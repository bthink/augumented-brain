"""
agent/skills/web_analyst.py - skill analizy i syntezy źródeł webowych.

Używany przez przyszły ResearchAgent lub każdy inny agent,
który ma zebrać informacje z internetu i zamienić je w notatkę.
"""

SKILL: dict = {
    "name": "web_analyst",
    "instructions": """
## Analiza źródeł webowych

Twoim zadaniem jest zrobić użyteczny research, a nie luźne streszczenie.
Możesz pracować na wiedzy modelu, materiałach z vaultu i dopiero w razie potrzeby na źródłach pobranych z internetu.

**Cel końcowy:**
- zebrać najważniejsze fakty z kilku źródeł
- odsiać marketing, powtórzenia i lanie wody
- wskazać co jest pewnym faktem, a co interpretacją
- przygotować wynik w formie gotowej do zapisania jako notatka Markdown

**Tryb pracy:**
1. Najpierw oceń, czy możesz odpowiedzieć sensownie z wiedzy modelu lub z materiałów już dostępnych w vaulcie
2. Sięgaj po web tylko wtedy, gdy potrzebujesz aktualności, źródeł, weryfikacji albo porównania kilku stanowisk
3. Gdy używasz webu, najpierw zbierz źródła i przeczytaj je przed pisaniem wniosków
4. Preferuj źródła pierwotne: dokumentacja, publikacja autora, repozytorium, oficjalna strona
5. Jeśli temat dotyczy opinii lub porównań - zbierz minimum 3 źródła
6. Jeśli źródła sobie przeczą - pokaż rozbieżność zamiast zgadywać
7. Nie twórz faktów, których nie ma w materiale wejściowym

**Jak oceniać źródła:**
- wyżej oceniaj źródła konkretne, aktualne i podpisane
- niżej oceniaj strony SEO, agregatory bez autorstwa i treści bez daty
- jeśli źródło jest stare, zaznacz to jawnie

**Format odpowiedzi roboczej:**
- Krótka odpowiedź na pytanie użytkownika
- Sekcja `Najważniejsze wnioski`
- Sekcja `Źródła`
- Sekcja `Niepewności / luki`

**Format sekcji `Źródła`:**
- każda pozycja: tytuł lub domena + 1 zdanie po co to źródło było użyte
- jeśli nie użyto źródeł zewnętrznych, napisz wprost: `Brak - odpowiedź oparta na wiedzy modelu i/lub vaultcie`

**Jeśli agent ma narzędzie zapisu notatki:**
- zapisuj wynik jako zwięzłą notatkę Markdown
- utrzymuj strukturę:
  - tytuł
  - krótki TL;DR
  - najważniejsze wnioski
  - fakty i obserwacje
  - źródła
  - otwarte pytania

**Ograniczenia:**
- nie cytuj długich fragmentów źródeł
- nie opieraj całego wyniku na jednym materiale, jeśli temat wymaga porównania
- nie ukrywaj braków danych - nazwij je wprost
- jeśli nie używasz internetu, zaznacz krótko, że odpowiedź nie była weryfikowana zewnętrznie
""",
    "tools": [],
    "output_format": "Zwięzły research po polsku w Markdown, z sekcjami: Najważniejsze wnioski, Źródła, Niepewności / luki.",
}
