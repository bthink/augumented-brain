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
├── 03_Knowledge/       → materiał referencyjny (m.in. podfoldery wg tematu — zob. poniżej „YouTube”)
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
      ├──────────────────┬──────────────────┬──────────────────┐
      ▼                  ▼                  ▼                  ▼
[ InboxAgent ]    [ TodoAgent ]    [ YoutubeAgent ]  [ ResearchAgent ]   ← sub_agents/
      │                  │                  │
      │    każdy sub-agent komponuje swoje skille
      │                  │
      ▼                  ▼
[ Skills ]               agent/skills/
  para_classifier        klasyfikacja do PARA
  clarifier              pytania doprecyzowujące
  time_estimator         priorytety TODO  (wkrótce)
  yt_transcript          transkrypcje YouTube → notatka
  web_analyst            analiza webowa i synteza źródeł
      │
      ▼
[ Tasks ]                tasks/  ← istniejący kod, bez zmian
  inbox.py  todo.py  web_utils.py  moc.py  media.py  orphans.py  proofread.py
      │
      ▼
[ Obsidian Vault ]       pliki .md na dysku / iCloud
```

### Routing w Orchestratorze

`Orchestrator._plan()` pyta LLM który agent wywołać. Zasady routingu (wprost w prompcie):
- `inbox` — wyłącznie pliki w `97_Inbox/`
- `youtube` — transkrypcja lub przeniesienie/poprawa notatki YT w `03_Knowledge`
- `research` — pytania o vault, pytania ogólne, research z/bez zapisu
- fallback: jeśli LLM nie wskaże żadnego znanego agenta → `research`

`Orchestrator.__init__` ma domyślnie `dry_run=False` (zapis live). `--dry-run` w CLI nadpisuje tę wartość.

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
├── config.py                 # VAULT_PATH, AREAS, stałe (w tym MEDIA_FILE)
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
│       ├── time_estimator.py  # ✅ priorytety dla TODO
│       ├── yt_transcript.py   # ✅ transkrypcje YouTube → notatka w vaulcie
│       └── web_analyst.py     # ✅ analiza i synteza źródeł webowych
│
├── sub_agents/
│   ├── inbox_agent.py        # ✅ klasyfikuje i przenosi notatki z Inbox; obsługuje media
│   ├── todo_agent.py         # ✅ opakowuje tasks/todo.py
│   ├── youtube_agent.py      # ✅ YT → notatka; folder + hub wg YT_KNOWLEDGE_BY_CATEGORY (config)
│   └── research_agent.py     # ✅ research: vault + internet + zapis notatki
│
└── tasks/                    # istniejący kod silnika — sub-agenty go wywołują
    ├── todo.py               # ✅ parsuje i grupuje TODO.md
    ├── inbox.py              # ✅ klasyfikacja legacy (bez agenta); obsługuje media
    ├── web_utils.py          # ✅ wspólne narzędzia HTTP: search_web, read_webpage, fetch_page
    ├── moc.py                # 🔲 aktualizacja notatek agregujących
    ├── media.py              # 🔲 podsumowania YT i mediów
    ├── orphans.py            # 🔲 detekcja osieroconych notatek
    └── proofread.py          # 🔲 korekta językowa
```

---

## Jak działają skille

Skill to composowalny blok instrukcji - paczka trzech rzeczy:

```python
SKILL = {
    "name": "para_classifier",
    "instructions": "...",      # wchodzi do system promptu agenta
    "tools": [],                # narzędzia których wymaga ten skill
    "output_format": "...",     # oczekiwany format outputu (opcjonalnie)
}
```

Agent przy inicjalizacji deklaruje listę skilli. Loader (`skills/__init__.py`) składa je w jeden system prompt. Instrukcje mogą zawierać `{AREAS}` i inne placeholdery z kontekstu sesji.

**Rejestr skilli** - żeby dodać nowy skill:
1. Utwórz `agent/skills/nazwa.py` ze słownikiem `SKILL`
2. Dodaj import i wpis do `REGISTRY` w `agent/skills/__init__.py`
3. Dodaj nazwę do `SKILLS = [...]` w sub-agencie który go potrzebuje

### `web_analyst`

Skill `web_analyst` jest już dostępny w rejestrze skilli i daje agentowi reguły syntezy researchu z internetu:
- preferencja dla źródeł pierwotnych
- rozdzielenie faktów od interpretacji
- jawne oznaczanie sprzeczności i luk
- wynik w formacie gotowym do zapisania jako notatka Markdown

Skill sam nie pobiera stron - robi to `ResearchAgent`, który dostarcza mu narzędzia do wyszukiwania, odczytu źródeł, przeglądu vaultu i zapisu notatek.

### `ResearchAgent`

`ResearchAgent` używa skilli `clarifier` i `web_analyst`. Obsługuje dwa rodzaje zadań:
- **pytania ogólne i research** — może korzystać z vaultu, internetu lub samej wiedzy modelu
- **pytania o notatki w vaulcie** — np. "przeczytaj moją notatkę o X i opowiedz mi o Y"

Jest domyślnym agentem dla zapytań, których Orchestrator nie potrafi przypisać do bardziej wyspecjalizowanego agenta.

Standardowy przepływ:
1. ocenia, czy wystarczy wiedza modelu
2. opcjonalnie sprawdza podobne notatki przez `search_vault`
3. opcjonalnie zbiera wyniki przez `search_web`
4. opcjonalnie czyta wybrane strony przez `read_webpage`
5. syntetyzuje wnioski według zasad `web_analyst`
6. opcjonalnie zapisuje wynik do `03_Knowledge/Research` przez `save_research_note` — **zapis nie jest obowiązkowy**, zależy od prośby użytkownika

Implementacja nie wymaga dodatkowych bibliotek HTTP — zarówno `ResearchAgent`, jak i `InboxAgent` korzystają z helpera `tasks/web_utils.py` (standardowa biblioteka Pythona + opcjonalnie `certifi`).

---

## Inbox media → watchlista (`InboxAgent`)

Notatki w `97_Inbox/` mogą być skrótami do filmów, seriali, książek lub gier — np. treść `film hoppers` lub `książka Dune`. `InboxAgent` rozpoznaje ten wzorzec i obsługuje go automatycznie.

**Przepływ:**

1. `list_inbox_notes` + `read_note` — agent odczytuje treść
2. Rozpoznaje prefiks: `film `, `serial `, `książka `, `gra ` → typ medium + tytuł
3. Dla **filmów i seriali**: `search_web("[tytuł] IMDB rating genre")` → opcjonalnie `read_webpage` dla szczegółów → wyciąga ocenę IMDB i gatunek
4. Dla **książek i gier**: sam gatunek (bez IMDB)
5. `save_to_watchlist(title, media_type, description)` — dopisuje wpis do odpowiedniej sekcji w `04_Ideas/Do obejrzenia i przeczytania.md` (sekcje: `**Filmy**`, `**Książki**`, `**Gry**`, `**Inne**`)
6. `delete_note` — usuwa notatkę z Inboxu

**Format wpisu w watchliście:**

```
- Hoppers (2026) — Animacja, Sci-Fi | ⭐ 7.7/10 IMDB
- Dune — Science Fiction
```

**Narzędzia w `InboxAgent`:** `save_to_watchlist`, `search_web`, `read_webpage` (HTTP przez `tasks/web_utils`).

**Ścieżka legacy (`tasks/inbox.py`):** funkcja `lookup_media()` + `apply_media()` obsługują to samo w trybie wsadowym bez agenta (flaga `--legacy`).

---

## Transkrypcje YouTube → notatka (`YoutubeAgent`, skill `yt_transcript`)

`YoutubeAgent` (`sub_agents/youtube_agent.py`) pobiera transkrypcję przez `youtube-transcript-api` (narzędzie `get_yt_transcript`); model wybiera **jedną kategorię** treści. Zapis notatki (`save_note`) jest spójny z konfiguracją — folder docelowy i **wikilink do notatki hub** nie są zgadywane ad hoc przez model, tylko wynikają z mapy w `config.py`.

**Źródło prawdy:** `YT_KNOWLEDGE_BY_CATEGORY` w `config.py` — dla każdej kategorii para `(podfolder względem 03_Knowledge, tytuł notatki hub)`. Z pliku `.md` powstaje m.in. frontmatter `category: …` oraz linia `[[tytuł hubu]]` (tytuł musi odpowiadać nazwie notatki w Obsidianie; jeśli w vaultcie używasz innych nazw hubów, zmień drugi element pary w mapie).

**Domyślne mapowanie kategorii** (skrót):

| Kategoria   | Podfolder w `03_Knowledge` | Hub (przykład)   |
|-------------|----------------------------|------------------|
| ai          | `IT`                       | `[[IT]]`         |
| it          | `IT`                       | `[[IT]]`         |
| zdrowie     | `Zdrowie`                  | `[[Zdrowie]]`    |
| inne        | `YT_summaries`             | `[[Yt summaries]]` |

Lista dozwolonych kategorii: `YT_CATEGORIES` (klucze `YT_KNOWLEDGE_BY_CATEGORY`). Podfoldery są tworzone przy zapisie, jeśli nie istnieją.

**Nadpisanie ścieżki:** parametr `folder` w `save_note` jest **opcjonalny** — używany tylko gdy użytkownik wyraźnie prosi o inny podfolder niż wynika z kategorii (pojedynczy segment nazwy, bez `..` i ścieżek).

**Defensywna obsługa `category`:** `execute_tool` w `YoutubeAgent` używa `.get("category")` zamiast `["category"]`. Jeśli model nie prześle pola (mimo że jest `required` w schemacie), agent dostaje czytelny komunikat błędu i może wywołać narzędzie ponownie z brakującym parametrem — zamiast rzucać `KeyError`.

Implementacja skilla: `agent/skills/yt_transcript.py`.

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
- [x] `TodoAgent` — opakowanie tasks/todo.py
- [x] `YoutubeAgent` + skill `yt_transcript` — transkrypcja YT → notatka w `03_Knowledge` (podfolder i `[[hub]]` z `YT_KNOWLEDGE_BY_CATEGORY`)
- [x] `InboxAgent` media handling — rozpoznawanie `film/serial/książka/gra [tytuł]`, lookup IMDB (filmy/seriale), zapis do watchlisty, usunięcie z Inboxu
- [x] `tasks/web_utils.py` — wspólne HTTP helpers (DuckDuckGo, fetch page) reużywane przez `InboxAgent` i `ResearchAgent`
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
- [ ] `media.py` — dalsza integracja mediów (YoutubeAgent już obsługuje YT)
- [ ] `proofread.py` jako sub-agent z wyborem obszaru
- [ ] Integracja LM Studio (`qwen2.5-14b-instruct`) jako fallback offline

---

## Otwarte pytania

- Czy `process_daily.py` (LM Studio) wchodzi do tego projektu czy zostaje osobno?
- Kiedy RAG staje się potrzebny? (przy ilu notatkach / jakich przypadkach użycia?)
- Telegram jako interfejs w Fazie 3 (Slack odpada — zbyt duży overhead dla personal use)
