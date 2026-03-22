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
from config import VAULT_PATH, AREAS

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
            case "ask_user":
                return self.ask_user(tool_args["question"])
            case _:
                return super().execute_tool(tool_name, tool_args)

    def run(self, task: str = "") -> AgentResult:
        """Uruchamia agenta. Domyślne zadanie jeśli nie podano."""
        if not task:
            task = (
                f"Przejrzyj wszystkie notatki w 97_Inbox/. Dla każdej:\n"
                f"1. Przeczytaj zawartość\n"
                f"2. Jeśli pusta lub bez wartości — usuń\n"
                f"3. Klasyfikuj do odpowiedniego folderu PARA\n"
                f"4. Przenieś (chyba że dry_run=True — wtedy tylko zaraportuj co byś zrobił)\n"
                f"5. Na końcu podsumuj co zrobiłeś\n\n"
                f"dry_run={self.dry_run}. Obszary: {', '.join(AREAS)}"
            )
        return super().run(task)

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
