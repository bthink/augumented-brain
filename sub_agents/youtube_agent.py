"""
sub_agents/youtube_agent.py — agent pobierający transkrypcje z YouTube i tworzący notatki w vaulcie.

Narzędzia:
    - get_yt_transcript: pobiera transkrypcję filmu
    - save_note: zapisuje notatkę .md do 03_Knowledge w vaulcie
    - ask_user: pyta o decyzję gdy potrzeba
"""

import json
import logging
from datetime import date
from pathlib import Path

from openai import OpenAI
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled

from agent.base_agent import BaseAgent, AgentResult
from agent.skills.yt_transcript import YT_TRANSCRIPT_TOOLS, fetch_transcript
from config import VAULT_PATH, FOLDERS

logger = logging.getLogger(__name__)

YOUTUBE_TOOLS = YT_TRANSCRIPT_TOOLS + [
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": (
                "Zapisuje notatkę Markdown do folderu 03_Knowledge w vaulcie Obsidian. "
                "Używaj po pobraniu i opracowaniu transkrypcji."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Nazwa pliku bez rozszerzenia, np. 'Rick Astley - Never Gonna Give You Up'",
                    },
                    "content": {
                        "type": "string",
                        "description": "Pełna treść notatki w formacie Markdown",
                    },
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Zadaje pytanie użytkownikowi i czeka na odpowiedź.",
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


class YoutubeAgent(BaseAgent):
    SKILLS = ["yt_transcript"]
    MAX_ITERATIONS = 8
    MODEL = "gpt-4o-mini"

    def __init__(self, client: OpenAI, dry_run: bool = False):
        super().__init__(client=client, context={"dry_run": dry_run})
        self.dry_run = dry_run
        self._knowledge_dir = VAULT_PATH / FOLDERS["knowledge"]

    def get_tools(self) -> list[dict]:
        return YOUTUBE_TOOLS

    def execute_tool(self, tool_name: str, tool_args: dict) -> str:
        match tool_name:
            case "get_yt_transcript":
                return self._get_transcript(**tool_args)
            case "save_note":
                return self._save_note(tool_args["filename"], tool_args["content"])
            case "ask_user":
                return self.ask_user(tool_args["question"])
            case _:
                return super().execute_tool(tool_name, tool_args)

    def run(self, task: str = "") -> AgentResult:
        if not task:
            task = "Zapytaj użytkownika o link do filmu YouTube, pobierz transkrypcję i stwórz notatkę w vaulcie."
        else:
            task = (
                f"{task}\n\n"
                "WAŻNE: Po pobraniu transkrypcji OBOWIĄZKOWO wywołaj save_note "
                "żeby zapisać notatkę do vaultu. Nie kończ bez zapisania notatki."
            )
        return super().run(task)

    # ------------------------------------------------------------------
    # Implementacje narzędzi
    # ------------------------------------------------------------------

    def _get_transcript(self, url: str, lang: str = "pl,en", include_meta: bool = False) -> str:
        try:
            result = fetch_transcript(url, lang=lang, include_meta=include_meta)
            return json.dumps(result, ensure_ascii=False)
        except ValueError as e:
            return f"BŁĄD: {e}"
        except TranscriptsDisabled:
            return "BŁĄD: Transkrypcje są wyłączone dla tego filmu."
        except NoTranscriptFound:
            return f"BŁĄD: Nie znaleziono transkrypcji w językach: {lang}"
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas pobierania transkrypcji: {e}", exc_info=True)
            return f"BŁĄD: {e}"

    def _save_note(self, filename: str, content: str) -> str:
        if self.dry_run:
            preview = content[:300] + ("..." if len(content) > 300 else "")
            return f"[DRY RUN] Zapisałbym notatkę '{filename}.md' do 03_Knowledge:\n{preview}"

        safe_name = "".join(c for c in filename if c not in r'\/:*?"<>|').strip()
        if not safe_name:
            return "BŁĄD: Nieprawidłowa nazwa pliku."

        target = self._knowledge_dir / f"{safe_name}.md"

        if not self._knowledge_dir.exists():
            return f"BŁĄD: Folder {self._knowledge_dir} nie istnieje."

        if target.exists():
            return (
                f"BŁĄD: Plik '{target.name}' już istnieje. "
                "Wybierz inną nazwę lub potwierdź nadpisanie."
            )

        try:
            target.write_text(content, encoding="utf-8")
            logger.info(f"Zapisano notatkę: {target}")
            return f"Zapisano notatkę: {target.name}"
        except OSError as e:
            logger.error(f"Błąd zapisu pliku {target}: {e}", exc_info=True)
            return f"BŁĄD podczas zapisu: {e}"
