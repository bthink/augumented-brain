# Augmented Brain — architektura i cele projektu

> Dokument referencyjny. Aktualizuj gdy zmienia się architektura lub cele.
> Repozytorium: `bthink/augumented-brain`

---

## Czym jest ten projekt

Augmented Brain to osobisty system AI do zarządzania wiedzą w Obsidianie (vault zorganizowany według frameworku PARA). System działa z terminala — na żądanie lub przez cron — i wykonuje operacje na plikach markdown bezpośrednio w vaulcie synchronizowanym przez iCloud.

Cel nadrzędny: **vault który sam się ogarnia**. Notatki z telefonu trafiają gdzie trzeba, TODO jest zawsze posortowane, a na żądanie system potrafi zrobić research i zapisać wyniki jako notatkę.

---

## Struktura vaultu (PARA)

```
Bf-vault/
├── 00_System/          → TODO.md i pliki systemowe
├── 01_Projects/        → projekty z deadlinem i konkretnym wynikiem
├── 02_Areas/           → obszary życia bez końca (AI, Money, Photography, Portfolio, Praca)
├── 03_Knowledge/       → materiał referencyjny
├── 04_Ideas/           → luźne pomysły, rzeczy do obejrzenia/przeczytania
├── 97_Inbox/           → surowe notatki z telefonu — tu trafia wszystko
├── 98_Templates/       → szablony notatek
└── 99_Archive/         → nieaktywne, zakończone
```

---

## Stack techniczny

| Warstwa | Technologia |
|---|---|
| Język | Python 3.13 |
| LLM (główny) | OpenAI API — `gpt-4o-mini` |
| LLM (offline) | LM Studio — `qwen2.5-14b-instruct` (zaimplementowany w `process_daily.py`, do integracji) |
| Operacje na plikach | Python + Obsidian CLI (gdzie potrzeba aktualizacji wikilinków) |
| Konfiguracja | `python-dotenv` |
| RAG | chromadb lokalnie — Faza 2, jeszcze nie wdrożony |

**Dlaczego Python, nie JS:** istniejący kod, naturalny ekosystem dla AI (chromadb, sentence-transformers, fastapi), brak potrzeby frontendu.

**Dlaczego nie LangGraph:** przy dziesiątkach notatek to przerost. Zwykła pętla ReAct w Pythonie jest wystarczająca i daje pełną kontrolę.

---

## Architektura systemu

### Warstwy (od góry do dołu)

```
[ Użytkownik ]
      │  komenda w języku naturalnym
      ▼
[ Orchestrator ]          agent/orchestrator.py
      │  routuje do sub-agentów, zbiera wyniki
      ├──────────────────┬──────────────────┐
      ▼                  ▼                  ▼
[ InboxAgent ]    [ TodoAgent ]    [ ResearchAgent ]   ← sub_agents/
      │                  │                  │
      │    każdy sub-agent komponuje swoje skille
      │                  │
      ▼                  ▼
[ Skills ]               agent/skills/
  para_classifier        klasyfikacja do PARA
  clarifier              pytania doprecyzowujące
  time_estimator         priorytety TODO  (wkrótce)
  web_analyst            analiza webowa   (wkrótce)
      │
      ▼
[ Tasks ]                tasks/  ← istniejący kod, bez zmian
  inbox.py  todo.py  moc.py  media.py  orphans.py  proofread.py
      │
      ▼
[ Obsidian Vault ]       pliki .md na dysku / iCloud
```

### Kluczowa zasada: każdy nowy feature = nowy tool

Pętla agenta (`base_agent.py`) **nigdy nie jest modyfikowana**. Nowe możliwości dodaje się jako:
- nowy skill (blok instrukcji dla agenta)
- nowy tool (funkcja którą agent może wywołać)
- nowy sub-agent (jeśli zadanie jest wystarczająco złożone)

Dzięki temu Faza 3 nie rozbija Fazy 1.

---

## Pliki projektu

```
augumented-brain/
├── main.py                   # punkt wejścia — tryby: interaktywny, auto, jednorazowy
├── config.py                 # VAULT_PATH, AREAS, stałe
├── requirements.txt
├── run.sh
├── .env                      # NIE commitować
├── .gitignore
├── ARCHITECTURE.md           # ten plik
│
├── agent/
│   ├── base_agent.py         # klasa bazowa — pętla ReAct, ładowanie skilli
│   ├── orchestrator.py       # router komend do sub-agentów
│   └── skills/
│       ├── __init__.py       # rejestr skilli + loader
│       ├── clarifier.py      # ✅ zadaje max 2 pytania przed akcją
│       ├── para_classifier.py # ✅ klasyfikacja do PARA z confidence score
│       ├── time_estimator.py  # 🔲 priorytety dla TODO
│       └── web_analyst.py     # 🔲 analiza i synteza webowa
│
├── sub_agents/
│   ├── inbox_agent.py        # ✅ klasyfikuje i przenosi notatki z Inbox
│   ├── todo_agent.py         # 🔲 opakowuje tasks/todo.py
│   └── research_agent.py     # 🔲 Faza 3 — vault + internet
│
└── tasks/                    # istniejący kod silnika — sub-agenty go wywołują
    ├── todo.py               # ✅ parsuje i grupuje TODO.md
    ├── inbox.py              # ✅ klasyfikacja (stara wersja bez agenta)
    ├── moc.py                # 🔲 aktualizacja notatek agregujących
    ├── media.py              # 🔲 podsumowania YT i mediów
    ├── orphans.py            # 🔲 detekcja osieroconych notatek
    └── proofread.py          # 🔲 korekta językowa
```

---

## Jak działają skille

Skill to composowalny blok instrukcji — paczka trzech rzeczy:

```python
SKILL = {
    "name": "para_classifier",
    "instructions": "...",      # wchodzi do system promptu agenta
    "tools": [],                # narzędzia których wymaga ten skill
    "output_format": "...",     # oczekiwany format outputu (opcjonalnie)
}
```

Agent przy inicjalizacji deklaruje listę skilli. Loader (`skills/__init__.py`) składa je w jeden system prompt. Instrukcje mogą zawierać `{AREAS}` i inne placeholdery z kontekstu sesji.

**Rejestr skilli** — żeby dodać nowy skill:
1. Utwórz `agent/skills/nazwa.py` ze słownikiem `SKILL`
2. Dodaj import i wpis do `REGISTRY` w `agent/skills/__init__.py`
3. Dodaj nazwę do `SKILLS = [...]` w sub-agencie który go potrzebuje

---

## Jak działa pętla ReAct (base_agent.py)

ReAct = Reason → Act → Observe, w pętli.

```
zadanie
   │
   ▼
[LLM: co teraz zrobić?]
   │
   ├── chce wywołać narzędzie → execute_tool() → wynik do konwersacji → kolejna iteracja
   │
   └── ma odpowiedź → zwróć AgentResult i zakończ
```

Każda iteracja to jedno wywołanie API. Agent widzi całą historię konwersacji (narzędzia + wyniki). Limit iteracji (`MAX_ITERATIONS`) chroni przed nieskończoną pętlą.

**Clarification loop** — jeśli skill `clarifier` jest załadowany, agent może wywołać narzędzie `ask_user` zanim zacznie działać. W CLI to `input()`. W Fazie 3 (Telegram/Slack) — nadpisana metoda `ask_user()` w sub-agencie.

---

## Obsidian CLI

Od v1.12.4 (luty 2026) Obsidian ma oficjalne CLI. Używamy go **tylko do przenoszenia plików** — bo CLI automatycznie aktualizuje wikilinki w całym vaulcie. Zwykłe `shutil.move()` sypie linki.

```python
# InboxAgent._obsidian_move()
subprocess.run(["obsidian", "move", str(source), str(target)])
# fallback: os.rename() jeśli CLI niedostępne
```

Do czytania i edycji treści używamy Pythona bezpośrednio — CLI nie ma dobrego interfejsu do edycji bloków.

---

## Setup projektu (od zera)

```bash
git clone git@github.com:bthink/augumented-brain.git
cd augumented-brain

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # uzupełnij VAULT_PATH i OPENAI_API_KEY
```

### Wymagana struktura plików

Po sklonowaniu repo musi mieć dokładnie tę strukturę — brak któregokolwiek pliku powoduje `ModuleNotFoundError`:

```
augumented-brain/
├── main.py
├── config.py
├── .env
│
├── agent/
│   ├── __init__.py          ← wymagany (pusty)
│   ├── base_agent.py
│   ├── orchestrator.py
│   └── skills/
│       ├── __init__.py      ← wymagany (rejestr skilli, NIE pusty)
│       ├── clarifier.py
│       └── para_classifier.py
│
├── sub_agents/
│   ├── __init__.py          ← wymagany (pusty)
│   └── inbox_agent.py
│
└── tasks/
    ├── __init__.py          ← wymagany (pusty)
    ├── inbox.py
    └── todo.py
```

> **Uwaga:** `agent/skills/__init__.py` zawiera rejestr skilli — nie jest pustym plikiem. Zastąpienie go pustym plikiem spowoduje `ImportError` przy starcie agenta.

### Weryfikacja instalacji

```bash
# Powinno pokazać plan działania bez żadnych zmian w vaulcie
python3 main.py --dry-run "ogarnij inbox"
```

---

## Tryby uruchamiania

```bash
# interaktywny chat z orchestratorem
python main.py

# jednorazowa komenda
python main.py "ogarnij inbox"
python main.py "zrób research o n8n"

# tryb automatyczny dla cron (inbox + todo bez pytań)
python main.py --auto

# symulacja bez zapisu
python main.py --dry-run "ogarnij inbox"

# stare menu (kompatybilność wsteczna)
python main.py --legacy

# cron co godzinę
0 * * * * cd ~/dzikieProjekty/augumented-brain && source venv/bin/activate && python3 main.py --auto
```

---

## Fazy rozwoju

### Faza 1 — Agent core ✅ (w trakcie)

Fundament systemu. Pętla ReAct, composowalne skille, pierwsze sub-agenty.

- [x] `base_agent.py` — klasa bazowa z pętlą ReAct
- [x] `skills/clarifier.py` + `skills/para_classifier.py`
- [x] `InboxAgent` — pierwszy działający sub-agent
- [x] `Orchestrator` — router komend
- [x] Migracja z `obsidian-manager/` do nowej struktury — `tasks/inbox.py` i `tasks/todo.py` przeniesione, `config.py` scalony (dodano `OPENAI_API_KEY` i `FOLDERS`)
- [ ] `TodoAgent` — opakowanie tasks/todo.py
- [ ] Testy na żywych danych, dostrojenie promptów

### Faza 2 — RAG (kiedy zajdzie potrzeba)

Dodanie pamięci o vaulcie. Nowe narzędzie `search_vault` dla agentów.

- [ ] Indeks chromadb budowany przy starcie (lokalnie, plik na dysku)
- [ ] `search_vault(query)` jako tool w sub-agentach
- [ ] `ResearchAgent` korzystający z RAG + web search
- [ ] Inkrementalna aktualizacja indeksu po zmianach w vaulcie

**Stack:** `chromadb` + `text-embedding-3-small` (OpenAI) lub `sentence-transformers` (offline)

### Faza 3 — Interfejs messaging

Agent dostępny spoza terminala.

- [ ] FastAPI endpoint (30 linii) — odbiera komendy HTTP
- [ ] Telegram bot webhook → parsuje komendę → wywołuje orchestrator → odpowiada
- [ ] `ask_user()` w sub-agentach nadpisany by czekał na odpowiedź w Telegramie
- [ ] `.app` na pulpit (jak gmail-bot) przez `create_app.sh`

### Faza 4 — Nowe narzędzia (kolejność do ustalenia)

Każde to nowy sub-agent lub rozszerzenie istniejącego.

- [ ] OCR — skanowanie dokumentów → notatka w vaulcie
- [ ] Mailing — digest z vaultu na email
- [ ] `media.py` — integracja z narzędziem YT (ID: `d80ba065-4999-4bf4-a962-7a2142f14da6`)
- [ ] `proofread.py` jako sub-agent z wyborem obszaru
- [ ] Integracja LM Studio (`qwen2.5-14b-instruct`) jako fallback offline

---

## Otwarte pytania

- Czy `process_daily.py` (LM Studio) wchodzi do tego projektu czy zostaje osobno?
- Kiedy RAG staje się potrzebny? (przy ilu notatkach / jakich przypadkach użycia?)
- Telegram jako interfejs w Fazie 3 (Slack odpada — zbyt duży overhead dla personal use)