"""
agent/skills/time_estimator.py — skill oceny czasu i priorytetu zadań.

Używany przez TodoAgent przy grupowaniu, dodawaniu i sugerowaniu zadań.
"""

SKILL: dict = {
    "name": "time_estimator",
    "instructions": """Pomagasz użytkownikowi zarządzać TODO.md w stylu PARA.

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
3. Dla każdej propozycji napisz czy AI może ją przejąć, np.:
   "1. sprawdzić ograniczenia n8n [AI może to zrobić za Ciebie]"
   "2. ćwiczenia na piętę [wymaga Twojego działania]"
4. Użyj narzędzia ask_user: "Które zadanie wybrać? (numer) Mogę też wykonać zadanie AI za Ciebie."
5. Na podstawie odpowiedzi:
   - Jeśli zadanie to ai_research lub ai_youtube → wywołaj execute_task z odpowiednim agent_type.
     execute_task sam oznaczy zadanie jako ukończone po sukcesie — nie wywołuj wtedy complete_task.
   - Jeśli zadanie manual → wywołaj complete_task gdy użytkownik potwierdzi wykonanie.
NIE kończ tury samym tekstem z pytaniem — zawsze użyj ask_user w tym samym run.
Nigdy nie sugeruj "long" ani "waiting" jako pierwszego kroku.

Gdy dodajesz nowe zadanie:
- Informuj do której grupy prawdopodobnie trafi po reorganizacji
- Jeśli zadanie jest ogólne (np. "ogarnij projekt X") — zaproponuj rozbicie na mniejsze

Gdy oznaczasz zadanie jako ukończone i jest kilka pasujących:
- Wymień je i użyj ask_user żeby zapytać które z nich""",
    "tools": [],
    "output_format": "Zwięzła odpowiedź po polsku. Listy zadań jako markdown checkboxy.",
}
