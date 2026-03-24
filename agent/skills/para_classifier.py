"""
skills/para_classifier.py — skill klasyfikacji treści do struktury PARA.

Composowalny z InboxAgent, ResearchAgent i każdym agentem
który musi zdecydować gdzie coś trafi w vaulcie.
"""

SKILL: dict = {
    "name": "para_classifier",
    "instructions": """
## Klasyfikacja PARA

Klasyfikujesz treści do struktury PARA. Dostępne lokalizacje w vaulcie:

**01_Projects/** — ma deadline lub konkretny wynik końcowy, jest aktywny
**02_Areas/** — standard do utrzymania bez końca, bieżące obszary życia
  Dostępne obszary: {AREAS}
**03_Knowledge/** — materiał referencyjny, może być użyty w przyszłości
**04_Ideas/** — luźne pomysły, inspiracje, rzeczy do eksploracji
**97_Inbox/** — zostaw tu tylko jeśli naprawdę nie wiadomo gdzie to trafi
**99_Archive/** — nieaktywne, zakończone, historyczne

**Zasady klasyfikacji:**
1. Oceń treść, nie tylko tytuł — notatka "Bez nazwy 6" może być ideą lub taskiem
2. Jeśli pasuje do konkretnego obszaru (np. AI, Photography) — użyj go
3. Preferuj konkretność: 02_Areas/AI jest lepsze niż 03_Knowledge
4. Przy wątpliwościach między dwiema lokalizacjami — wybierz bardziej konkretną
5. Confidence < 0.6 oznacza że powinieneś zapytać użytkownika

**Ukończone akcje i sub-projekty** (frontmatter `status: done` lub tag `#done`/`#ukończone`):
6. Jeśli ukończona akcja/sub-projekt należy do aktywnego obszaru życia (np. Portfolio, Photography)
   → przenieś do **02_Areas/<obszar>** jako zapis historyczny (area pozostaje aktywna)
7. Jeśli ukończony był samodzielny projekt bez powiązania z aktywnym obszarem
   → przenieś do **99_Archive**
8. Zasada: obszar (Area) nigdy nie "kończy się" — kończą się konkretne akcje w nim

**Output klasyfikacji** (zawsze JSON):
```json
{{
  "folder": "02_Areas/AI",
  "confidence": 0.85,
  "reason": "Notatka dotyczy narzędzi AI do automatyzacji"
}}
```
""",
    "tools": [],
    "output_format": '{"folder": str, "confidence": float (0-1), "reason": str}',
}
