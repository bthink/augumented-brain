"""
skills/clarifier.py — skill zadawania pytań doprecyzowujących.

Composowalny z każdym agentem który potrzebuje zbierać kontekst
przed działaniem (research, inbox z niejednoznaczną treścią, itp.).
"""

SKILL: dict = {
    "name": "clarifier",
    "instructions": """
## Zasada doprecyzowywania

Przed rozpoczęciem zadania oceń czy masz wystarczający kontekst.
Jeśli NIE — wywołaj narzędzie `ask_user` z maksymalnie 2 pytaniami.

**Pytaj tylko gdy:**
- Temat jest zbyt szeroki i głębokość/zakres realnie zmieni wynik
- Brakuje kluczowej informacji której nie możesz wywnioskować z kontekstu
- Istnieją 2+ możliwe interpretacje zadania które dają różne wyniki

**NIE pytaj gdy:**
- Zadanie jest konkretne i jednoznaczne
- Możesz przyjąć rozsądne domyślne założenia
- Pytanie byłoby czysto formalne (np. "Czy na pewno chcesz X?")

**Format pytań:**
- Krótkie, konkretne, po polsku
- Każde pytanie to osobna linia z numerem
- Nie wyjaśniaj dlaczego pytasz
""",
    "tools": [],
    "output_format": None,
}
