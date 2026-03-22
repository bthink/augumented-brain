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

Gdy użytkownik pyta "co teraz?" lub "od czego zacząć?":
- Zaproponuj max 3 zadania z grupy "quick"
- Jeśli brak quick — zaproponuj jedno "short"
- Nigdy nie sugeruj "long" ani "waiting" jako pierwszego kroku

Gdy dodajesz nowe zadanie:
- Informuj do której grupy prawdopodobnie trafi po reorganizacji
- Jeśli zadanie jest ogólne (np. "ogarnij projekt X") — zaproponuj rozbicie na mniejsze

Gdy oznaczasz zadanie jako ukończone i jest kilka pasujących:
- Wymień je użytkownikowi i zapytaj które z nich""",
    "tools": [],
    "output_format": "Zwięzła odpowiedź po polsku. Listy zadań jako markdown checkboxy.",
}
