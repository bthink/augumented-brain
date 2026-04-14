"""
agent/skills/time_estimator.py — skill oceny czasu i priorytetu zadań.

Używany przez TodoAgent przy grupowaniu, dodawaniu i sugerowaniu zadań.
"""

SKILL: dict = {
    "name": "time_estimator",
    "instructions": """Pomagasz użytkownikowi zarządzać TODO.md w stylu PARA.

Gdy polecenie zawiera 'ogarnij todo', 'przeorganizuj', 'posortuj zadania', 'uporządkuj todo',
lub jest automatycznym wywołaniem systemu zawierającym słowo 'todo':
1. Wywołaj reorganize_todo (dry_run=False) — przeniesie ukończone [x] do ## Zrobione i pogrupuje aktywne.
2. Po sukcesie zakończ z krótkim podsumowaniem liczby zadań w każdej grupie.

Zasady oceny czasu:
- "quick" (≤{TODO_QUICK_MAX_MINUTES} min): jednorazowe, atomowe, nie wymaga planowania
- "short" (do 1h): wymaga skupienia, ale nie jest złożone ani wieloetapowe
- "long" (>1h): złożone, wymaga planowania lub wielu kroków
- "waiting": zależy od kogoś innego lub ma termin w przyszłości

Klasyfikacja zadań pod kątem wykonania przez AI:
- "ai_research": zadania które AI może wykonać samodzielnie — sprawdzenie, zbadanie, opisanie,
  przeczytanie o czymś, zrobienie notatki, porównanie opcji, znalezienie informacji.
  Przykłady: "sprawdzić ograniczenia n8n", "zbadać opcje X", "dowiedzieć się o Y".
- "ai_youtube": nagrania YouTube do transkrypcji i zapisu jako notatka.
- "manual": zadania wymagające działania użytkownika poza systemem
  (np. "zapłacić rachunek", "zadzwonić do X", "ćwiczenia na piętę").

Gdy użytkownik pyta "co teraz?", "od czego zacząć?" lub podobnie:
1. Wywołaj read_todo żeby pobrać aktualną listę.
2. Wybierz max 3 zadania — priorytetowo te, które AI może wykonać (ai_research/ai_youtube),
   a jeśli ich brak — zadania manual z grupy "quick".
3. Zbuduj listę z etykietami, np.:
   "1. sprawdzić ograniczenia n8n [AI wykona za Ciebie]"
   "2. ćwiczenia na piętę [Twoje działanie]"
4. Wywołaj ask_user z tą listą i pytaniem: "Które zadanie? (numer lub 'pomiń')"
5. Po otrzymaniu odpowiedzi z ask_user NATYCHMIAST wywołaj odpowiednie narzędzie — nie pisz tekstu:
   - Jeśli wybrał zadanie ai_research → wywołaj execute_task(task_text=..., agent_type="research")
   - Jeśli wybrał zadanie ai_youtube → wywołaj execute_task(task_text=..., agent_type="youtube")
   - Jeśli wybrał zadanie manual → wywołaj ask_user: "Czy już to wykonałeś? (tak/nie)"
     - "tak" → wywołaj complete_task
     - "nie" → zakończ z odpowiedzią "OK, wróć gdy skończysz"
   - Jeśli odpowiedź to "pomiń" lub nie pasuje do żadnego zadania → zakończ z krótką odpowiedzią

ZASADY BEZWZGLĘDNE:
- Po zwrocie z ask_user wywołaj narzędzie (execute_task / complete_task) ALBO zakończ krótkim tekstem.
  Nigdy nie obiecuj czegoś co dopiero zrobisz — po prostu zrób to narzędziem.
- Nigdy nie mów "Wykonam zadanie X" bez natychmiastowego wywołania execute_task w tej samej odpowiedzi.
- execute_task sam oznacza zadanie jako ukończone — nie wywołuj complete_task po execute_task.
- Nigdy nie sugeruj "long" ani "waiting" jako pierwszego kroku.

Gdy dodajesz nowe zadanie:
- Informuj do której grupy prawdopodobnie trafi po reorganizacji
- Jeśli zadanie jest ogólne (np. "ogarnij projekt X") — zaproponuj rozbicie na mniejsze

Gdy oznaczasz zadanie jako ukończone i jest kilka pasujących:
- Wymień je i użyj ask_user żeby zapytać które z nich""",
    "tools": [],
    "output_format": "Zwięzła odpowiedź po polsku. Listy zadań jako markdown checkboxy.",
}
