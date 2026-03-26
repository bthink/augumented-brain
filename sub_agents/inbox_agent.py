"""
sub_agents/inbox_agent.py — agent przetwarzający notatki z 97_Inbox/.

Dziedziczy BaseAgent, używa skilli: para_classifier.
Opcjonalnie clarifier gdy notatka jest niejednoznaczna.

Narzędzia:
    - read_note: czyta treść notatki
    - classify_note: klasyfikuje notatkę do PARA (przez LLM + skill)
    - move_note: przenosi plik (przez Obsidian CLI lub shutil jako fallback)
    - delete_note: usuwa pustą notatkę
    - ask_user: pyta użytkownika o decyzję (dziedziczone z BaseAgent)
"""

import json
import os
import subprocess
import logging
from pathlib import Path

from openai import OpenAI

from agent.base_agent import BaseAgent, AgentResult
from config import MEDIA_FILE, VAULT_PATH, AREAS
from tasks.web_utils import search_web as _search_web_fn, read_webpage as _read_webpage_fn
from tasks.todo import add_task as _add_task

logger = logging.getLogger(__name__)

# Narzędzia w formacie OpenAI function calling
INBOX_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_inbox_notes",
            "description": "Zwraca listę wszystkich plików w 97_Inbox/",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_note",
            "description": "Czyta zawartość notatki z vaultu",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Nazwa pliku (bez ścieżki), np. 'Bez nazwy 6.md'",
                    }
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_note",
            "description": "Przenosi notatkę z Inbox do docelowego folderu PARA. Aktualizuje wikilinki przez Obsidian CLI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Nazwa pliku źródłowego"},
                    "target_folder": {
                        "type": "string",
                        "description": "Docelowy folder relative do vaultu, np. '02_Areas/AI'",
                    },
                    "add_backlink": {
                        "type": "string",
                        "description": "Opcjonalnie: nazwa MOC do dodania jako [[link]] w notatce, np. 'AI'",
                    },
                },
                "required": ["filename", "target_folder"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Usuwa pustą lub nieistotną notatkę z Inbox",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "reason": {"type": "string", "description": "Powód usunięcia (do raportu)"},
                },
                "required": ["filename", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_watchlist",
            "description": (
                "Dodaje film/książkę/grę/serial do notatki 'Do obejrzenia i przeczytania'. "
                "Używaj po zidentyfikowaniu notatki jako media. "
                "Dla filmów i seriali: pobierz ocenę IMDB i gatunek przez search_web, "
                "podaj jako description np. 'Animacja, Sci-Fi | ⭐ 7.7/10 IMDB'. "
                "Dla książek i gier: podaj tylko gatunek bez oceny IMDB."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Tytuł medium, np. 'Hoppers (2026)'",
                    },
                    "media_type": {
                        "type": "string",
                        "description": "Typ: film | serial | książka | gra | inne",
                    },
                    "description": {
                        "type": "string",
                        "description": "Gatunek i ocena, np. 'Animacja, Sci-Fi | ⭐ 7.7/10 IMDB'",
                    },
                },
                "required": ["title", "media_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Wyszukuje w sieci przez DuckDuckGo. "
                "Używaj do pobrania oceny IMDB i gatunku dla filmów/seriali. "
                "Przykładowe zapytanie: 'Hoppers 2026 film IMDB rating genre'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Fraza do wyszukania"},
                    "max_results": {
                        "type": "integer",
                        "description": "Maksymalna liczba wyników, domyślnie 5",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": (
                "Pobiera stronę i zwraca jej treść. "
                "Używaj po search_web żeby uzyskać szczegółowe dane (np. ze strony IMDB)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Pełny URL strony do przeczytania"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_todo",
            "description": (
                "Dodaje zadanie do TODO.md. "
                "Używaj gdy notatka zaczyna się od 'todo' — wyciągnij treść zadania (bez słowa 'todo') i dodaj. "
                "Po dodaniu usuń notatkę z Inbox przez delete_note."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_text": {
                        "type": "string",
                        "description": "Treść zadania (bez przedrostka 'todo'), np. 'sprawdzić backup Obsidian'",
                    }
                },
                "required": ["task_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Zadaje użytkownikowi pytanie i czeka na odpowiedź. Używaj tylko gdy classification confidence < 0.6.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Pytanie do użytkownika"}
                },
                "required": ["question"],
            },
        },
    },
]


class InboxAgent(BaseAgent):
    SKILLS = ["para_classifier"]
    MAX_ITERATIONS = 20  # może być dużo notatek
    MODEL = "gpt-4o-mini"

    def __init__(self, client: OpenAI, dry_run: bool = True):
        context = {
            "AREAS": ", ".join(AREAS),
            "dry_run": dry_run,
        }
        super().__init__(client=client, context=context)
        self.dry_run = dry_run
        self.inbox_path = Path(VAULT_PATH) / "97_Inbox"
        self.actions_taken: list[dict] = []  # log akcji do raportu

    def get_tools(self) -> list[dict]:
        return INBOX_TOOLS

    def execute_tool(self, tool_name: str, tool_args: dict) -> str:
        match tool_name:
            case "list_inbox_notes":
                return self._list_inbox_notes()
            case "read_note":
                return self._read_note(tool_args["filename"])
            case "move_note":
                return self._move_note(
                    tool_args["filename"],
                    tool_args["target_folder"],
                    tool_args.get("add_backlink"),
                )
            case "delete_note":
                return self._delete_note(tool_args["filename"], tool_args["reason"])
            case "save_to_watchlist":
                return self._save_to_watchlist(
                    tool_args["title"],
                    tool_args["media_type"],
                    tool_args.get("description", ""),
                )
            case "search_web":
                return _search_web_fn(tool_args["query"], tool_args.get("max_results", 5))
            case "read_webpage":
                return _read_webpage_fn(tool_args["url"])
            case "add_to_todo":
                return self._add_to_todo(tool_args["task_text"])
            case "ask_user":
                return self.ask_user(tool_args["question"])
            case _:
                return super().execute_tool(tool_name, tool_args)

    def run(self, task: str = "") -> AgentResult:
        """Uruchamia agenta. Domyślne zadanie jeśli nie podano."""
        if not task:
            task = self._build_task()
        result = super().run(task)

        # Weryfikacja: sprawdź czy inbox jest faktycznie pusty po zakończeniu.
        # Chroni przed pominięciem notatek (np. opóźnienie synchronizacji iCloud).
        remaining = self._get_remaining_notes()
        if remaining:
            logger.warning(
                "[InboxAgent] Po zakończeniu w inbox pozostało %d notatek: %s",
                len(remaining),
                remaining,
            )
            retry_task = (
                f"W 97_Inbox/ nadal znajdują się nieprzetwrzone notatki: {remaining}.\n"
                f"Przetwórz je tak samo jak poprzednie — przeczytaj, sklasyfikuj i wykonaj akcję.\n"
                f"dry_run={self.dry_run}. Obszary: {', '.join(AREAS)}"
            )
            retry_result = super().run(retry_task)
            combined_output = f"{result.output}\n\n---\n⚠️ Retry (pominięte notatki):\n{retry_result.output}"
            return AgentResult(
                success=retry_result.success,
                output=combined_output,
                data={**result.data, **retry_result.data},
            )

        return result

    def _build_task(self) -> str:
        return (
            f"Przejrzyj wszystkie notatki w 97_Inbox/. Dla każdej:\n"
            f"1. Przeczytaj zawartość.\n"
            f"2. Jeśli pusta lub bez wartości — usuń (delete_note).\n"
            f"3. Sprawdź czy treść notatki zaczyna się od 'todo' (case-insensitive, może być 'todo:' lub 'todo '):\n"
            f"   a. Wyciągnij treść zadania (usuń przedrostek 'todo' i opcjonalne dwukropki/spacje).\n"
            f"   b. Wywołaj add_to_todo z tą treścią.\n"
            f"   c. Usuń notatkę (delete_note).\n"
            f"4. Sprawdź czy to notatka medialna — treść zaczyna się od 'film ', 'serial ',\n"
            f"   'książka ', 'gra ', lub jest wyraźnym tytułem do obejrzenia/przeczytania:\n"
            f"   a. Jeśli film lub serial — wyszukaj ocenę IMDB i gatunek przez search_web,\n"
            f"      np. '[tytuł] IMDB rating genre'. Przeczytaj wynik przez read_webpage jeśli potrzeba.\n"
            f"      Dla książek i gier NIE szukaj IMDB — podaj tylko gatunek jeśli go znasz.\n"
            f"   b. Wywołaj save_to_watchlist z tytułem, typem i opisem.\n"
            f"   c. Usuń notatkę (delete_note).\n"
            f"5. Sprawdź czy notatka jest oznaczona jako ukończona:\n"
            f"   - frontmatter zawiera 'status: done' lub 'status: ukończone'\n"
            f"   - LUB treść zawiera tag #done lub #ukończone\n"
            f"   Jeśli tak: zastosuj logikę ukończonych akcji z para_classifier (zasady 6-8):\n"
            f"   - Akcja/sub-projekt powiązany z aktywnym obszarem ({', '.join(AREAS)}) → 02_Areas/<obszar>\n"
            f"   - Samodzielny zakończony projekt bez aktywnego obszaru → 99_Archive\n"
            f"6. Dla pozostałych notatek — klasyfikuj do folderu PARA i przenieś (move_note).\n"
            f"7. Na końcu podsumuj co zrobiłeś.\n\n"
            f"dry_run={self.dry_run}. Obszary: {', '.join(AREAS)}"
        )

    def _get_remaining_notes(self) -> list[str]:
        """Zwraca listę plików .md pozostałych w inbox po zakończeniu agenta."""
        if not self.inbox_path.exists():
            return []
        return [f.name for f in self.inbox_path.iterdir() if f.suffix == ".md"]

    # ------------------------------------------------------------------
    # Implementacje narzędzi
    # ------------------------------------------------------------------

    def _list_inbox_notes(self) -> str:
        if not self.inbox_path.exists():
            return "BŁĄD: Folder 97_Inbox nie istnieje"

        files = [f.name for f in self.inbox_path.iterdir() if f.suffix == ".md"]
        if not files:
            return "Inbox jest pusty."

        return json.dumps(files, ensure_ascii=False)

    def _read_note(self, filename: str) -> str:
        path = self.inbox_path / filename
        if not path.exists():
            return f"BŁĄD: Plik '{filename}' nie istnieje w Inbox"

        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return "[PUSTA NOTATKA]"

        # Ogranicz do 2000 znaków — wystarczy do klasyfikacji
        if len(content) > 2000:
            return content[:2000] + "\n\n[...treść skrócona...]"
        return content

    def _move_note(self, filename: str, target_folder: str, add_backlink: str | None) -> str:
        source = self.inbox_path / filename
        target_dir = Path(VAULT_PATH) / target_folder
        target = target_dir / filename

        action = {
            "action": "move",
            "file": filename,
            "from": "97_Inbox",
            "to": target_folder,
            "backlink": add_backlink,
        }

        if self.dry_run:
            self.actions_taken.append({**action, "status": "dry_run"})
            return f"[DRY RUN] Przeniósłbym '{filename}' → {target_folder}"

        if not source.exists():
            return f"BŁĄD: '{filename}' nie istnieje"

        # Dodaj backlink do notatki przed przeniesieniem
        if add_backlink:
            content = source.read_text(encoding="utf-8")
            if f"[[{add_backlink}]]" not in content:
                source.write_text(content + f"\n\n[[{add_backlink}]]", encoding="utf-8")

        # Przenieś przez Obsidian CLI (aktualizuje wikilinki)
        # Fallback na shutil jeśli CLI niedostępne
        result = self._obsidian_move(source, target)
        self.actions_taken.append({**action, "status": "done" if result else "error"})
        return f"Przeniesiono '{filename}' → {target_folder}" if result else f"BŁĄD przy przenoszeniu '{filename}'"

    def _delete_note(self, filename: str, reason: str) -> str:
        path = self.inbox_path / filename
        action = {"action": "delete", "file": filename, "reason": reason}

        if self.dry_run:
            self.actions_taken.append({**action, "status": "dry_run"})
            return f"[DRY RUN] Usunąłbym '{filename}' ({reason})"

        if not path.exists():
            return f"BŁĄD: '{filename}' nie istnieje"

        path.unlink()
        self.actions_taken.append({**action, "status": "done"})
        return f"Usunięto '{filename}'"

    def _save_to_watchlist(self, title: str, media_type: str, description: str = "") -> str:
        if not MEDIA_FILE.exists():
            return f"BŁĄD: Nie znaleziono pliku watchlisty '{MEDIA_FILE}'"

        section_map = {
            "film":    "**Filmy**",
            "serial":  "**Filmy**",
            "książka": "**Książki**",
            "gra":     "**Gry**",
        }
        section = section_map.get(media_type.lower(), "**Inne**")
        desc = f" — {description}" if description else ""
        new_entry = f"- {title}{desc}\n"

        action = {
            "action": "watchlist",
            "title": title,
            "media_type": media_type,
            "section": section,
        }

        if self.dry_run:
            self.actions_taken.append({**action, "status": "dry_run"})
            return f"[DRY RUN] Dodałbym '{title}' do sekcji {section}"

        try:
            content = MEDIA_FILE.read_text(encoding="utf-8")
            if section in content:
                content = content.replace(section, f"{section}\n{new_entry}", 1)
            else:
                content += f"\n{section}\n{new_entry}\n"
            MEDIA_FILE.write_text(content, encoding="utf-8")
        except OSError as e:
            logger.error("Błąd zapisu watchlisty: %s", e)
            return f"BŁĄD: Nie udało się zapisać do watchlisty: {e}"

        self.actions_taken.append({**action, "status": "done"})
        return f"Dodano '{title}' do sekcji {section} w 'Do obejrzenia i przeczytania'"

    def _add_to_todo(self, task_text: str) -> str:
        action = {"action": "add_to_todo", "task": task_text}

        if self.dry_run:
            self.actions_taken.append({**action, "status": "dry_run"})
            return f"[DRY RUN] Dodałbym do TODO: '{task_text}'"

        try:
            success = _add_task(task_text)
        except Exception as e:
            logger.error("Błąd dodawania do TODO: %s", e, exc_info=True)
            return f"BŁĄD: Nie udało się dodać do TODO: {e}"

        if not success:
            return "BŁĄD: Plik TODO.md nie istnieje"

        self.actions_taken.append({**action, "status": "done"})
        return f"Dodano do TODO: '{task_text}'"

    def _obsidian_move(self, source: Path, target: Path) -> bool:
        """Próbuje przenieść przez Obsidian CLI, fallback na os.rename."""
        target.parent.mkdir(parents=True, exist_ok=True)

        # Próba przez Obsidian CLI
        try:
            result = subprocess.run(
                ["obsidian", "move", str(source), str(target)],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Obsidian CLI: przeniesiono {source.name}")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("Obsidian CLI niedostępne — używam os.rename")

        # Fallback
        try:
            os.rename(source, target)
            return True
        except Exception as e:
            logger.error(f"Błąd przenoszenia: {e}")
            return False
