"""
sub_agents/orphans_agent.py — agent do wykrywania osieroconych notatek.
"""

from __future__ import annotations

import json

from openai import OpenAI

from agent.base_agent import AgentResult, BaseAgent
from tasks.orphans import archive_note, find_orphan_notes, find_root_stray_notes

ORPHANS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_orphans",
            "description": (
                "Wykrywa osierocone notatki (bez backlinków) i zwraca listę "
                "ścieżek względnych w vault."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "archive_orphan",
            "description": "Przenosi wskazaną osieroconą notatkę do 99_Archive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Ścieżka notatki względem root vaultu.",
                    }
                },
                "required": ["relative_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_root_strays",
            "description": (
                "Znajduje pliki .md leżące bezpośrednio w root vaultu (poza podfolderami PARA). "
                "Takie notatki nie są przypisane do żadnej kategorii — powinny trafić do Inbox lub "
                "odpowiedniego folderu PARA."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Zadaje użytkownikowi pytanie i czeka na odpowiedź.",
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


class OrphansAgent(BaseAgent):
    MAX_ITERATIONS = 8
    MODEL = "gpt-4o-mini"

    def __init__(self, client: OpenAI, dry_run: bool = True):
        super().__init__(client=client, context={"dry_run": dry_run})
        self.dry_run = dry_run

    def get_tools(self) -> list[dict]:
        return ORPHANS_TOOLS

    def execute_tool(self, tool_name: str, tool_args: dict) -> str:
        match tool_name:
            case "find_orphans":
                return self._find_orphans()
            case "find_root_strays":
                return self._find_root_strays()
            case "archive_orphan":
                return self._archive_orphan(tool_args["relative_path"])
            case "ask_user":
                return self.ask_user(tool_args["question"])
            case _:
                return super().execute_tool(tool_name, tool_args)

    def run(self, task: str = "") -> AgentResult:
        effective_task = task or (
            "Znajdź osierocone notatki (bez backlinków). "
            "Wywołaj find_orphans i pokaż listę. "
            "Wywołaj też find_root_strays — jeśli znajdziesz pliki w root vaultu, zgłoś je osobno. "
            "Nie archiwizuj automatycznie bez wyraźnej prośby użytkownika."
        )
        return super().run(f"{effective_task}\n\ndry_run={self.dry_run}")

    def _find_orphans(self) -> str:
        orphans = find_orphan_notes()
        payload = {"count": len(orphans), "orphans": orphans}
        return json.dumps(payload, ensure_ascii=False)

    def _find_root_strays(self) -> str:
        strays = find_root_stray_notes()
        payload = {"count": len(strays), "root_strays": strays}
        return json.dumps(payload, ensure_ascii=False)

    def _archive_orphan(self, relative_path: str) -> str:
        if self.dry_run:
            return f"[DRY RUN] Przeniósłbym '{relative_path}' do 99_Archive."
        return archive_note(relative_path)
