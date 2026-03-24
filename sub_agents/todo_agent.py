"""
sub_agents/todo_agent.py — agent zarządzający plikiem TODO.md.

Dziedziczy BaseAgent, używa skilli: time_estimator.

Narzędzia:
    - read_todo: czyta i parsuje TODO.md
    - add_task: dodaje nowe zadanie
    - complete_task: oznacza zadanie jako ukończone
    - reorganize_todo: pełne przeliczenie i grupowanie przez AI
    - ask_user: pyta użytkownika o decyzję (gdy pasuje kilka zadań)
    - execute_task: deleguje zadanie do odpowiedniego agenta (research/youtube),
                    a po sukcesie oznacza je jako ukończone w TODO.md
"""

import json
import logging
from openai import OpenAI

from agent.base_agent import BaseAgent, AgentResult
from config import TODO_FILE, TODO_QUICK_MAX_MINUTES
from tasks.todo import (
    parse_tasks,
    add_task as todo_add_task,
    complete_task_by_text,
    process_todo,
)

logger = logging.getLogger(__name__)

TODO_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_todo",
            "description": "Czyta TODO.md i zwraca zadania podzielone na sekcje (aktywne i ukończone).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Dodaje nowe zadanie do TODO.md.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Treść zadania, np. 'kupić mleko'",
                    }
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": (
                "Oznacza zadanie jako ukończone. "
                "Jeśli pasuje więcej niż jedno zadanie — zwraca listę i NIE oznacza, "
                "wtedy użyj ask_user żeby użytkownik wybrał właściwe."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Fragment tekstu zadania, np. 'raport'",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorganize_todo",
            "description": (
                "Przebudowuje TODO.md: grupuje aktywne zadania przez AI "
                "(quick/short/long/waiting), archiwizuje ukończone. "
                "Używaj gdy użytkownik prosi o 'ogarnij todo' lub 'posortuj zadania'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dry_run": {
                        "type": "boolean",
                        "description": "Jeśli true — tylko podgląd bez zapisu. Domyślnie false.",
                    }
                },
                "required": [],
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
    {
        "type": "function",
        "function": {
            "name": "execute_task",
            "description": (
                "Deleguje zadanie TODO do wyspecjalizowanego agenta, który je wykona "
                "(np. zrobi research i zapisze notatkę), a po sukcesie oznacza zadanie "
                "jako ukończone w TODO.md. "
                "Używaj gdy zadanie nadaje się do automatycznego wykonania przez AI, "
                "np. 'sprawdź X', 'zbadaj Y', 'przeczytaj o Z'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_text": {
                        "type": "string",
                        "description": "Dokładna treść zadania z TODO.md, np. 'sprawdzić ograniczenia i płatności n8n'",
                    },
                    "agent_type": {
                        "type": "string",
                        "enum": ["research", "youtube"],
                        "description": (
                            "Który agent ma wykonać zadanie: "
                            "'research' — wyszukanie informacji, analiza, notatka; "
                            "'youtube' — transkrypcja i notatka z YouTube."
                        ),
                    },
                },
                "required": ["task_text", "agent_type"],
            },
        },
    },
]


class TodoAgent(BaseAgent):
    SKILLS = ["time_estimator"]
    MAX_ITERATIONS = 10
    MODEL = "gpt-4o-mini"

    def __init__(self, client: OpenAI, dry_run: bool = False):
        context = {
            "TODO_QUICK_MAX_MINUTES": TODO_QUICK_MAX_MINUTES,
            "dry_run": dry_run,
        }
        super().__init__(client=client, context=context)
        self.dry_run = dry_run

    def get_tools(self) -> list[dict]:
        return TODO_TOOLS

    def execute_tool(self, tool_name: str, tool_args: dict) -> str:
        match tool_name:
            case "read_todo":
                return self._read_todo()
            case "add_task":
                return self._add_task(tool_args["text"])
            case "complete_task":
                return self._complete_task(tool_args["query"])
            case "reorganize_todo":
                return self._reorganize_todo(tool_args.get("dry_run", False))
            case "ask_user":
                return self.ask_user(tool_args["question"])
            case "execute_task":
                return self._execute_task(tool_args["task_text"], tool_args["agent_type"])
            case _:
                return super().execute_tool(tool_name, tool_args)

    def run(self, task: str = "") -> AgentResult:
        if not task:
            task = (
                "Przeorganizuj TODO.md: pogrupuj aktywne zadania, "
                "zarchiwizuj stare ukończone.\n"
                f"dry_run={self.dry_run}"
            )
        return super().run(task)

    # ------------------------------------------------------------------
    # Implementacje narzędzi
    # ------------------------------------------------------------------

    def _read_todo(self) -> str:
        if not TODO_FILE.exists():
            return f"BŁĄD: Nie znaleziono pliku {TODO_FILE}"

        content = TODO_FILE.read_text(encoding="utf-8")
        tasks = parse_tasks(content)

        active = [t for t in tasks if not t.done]
        done = [t for t in tasks if t.done]

        result = {
            "active": [t.text for t in active],
            "total_active": len(active),
            "total_done": len(done),
        }
        return json.dumps(result, ensure_ascii=False)

    def _add_task(self, text: str) -> str:
        if self.dry_run:
            return f"[DRY RUN] Dodałbym zadanie: '{text}'"

        success = todo_add_task(text, TODO_FILE)
        if success:
            return f"Dodano zadanie: '{text}'"
        return f"BŁĄD: Nie udało się dodać zadania (plik {TODO_FILE} nie istnieje)"

    def _complete_task(self, query: str) -> str:
        if self.dry_run:
            return f"[DRY RUN] Oznaczyłbym jako ukończone zadanie pasujące do: '{query}'"

        matched, count = complete_task_by_text(query, TODO_FILE)

        if not matched:
            return f"Nie znaleziono żadnego aktywnego zadania pasującego do '{query}'"

        if len(matched) > 1:
            listed = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(matched))
            choice = self.ask_user(
                f"Znalazłem {len(matched)} pasujące zadania:\n{listed}\n"
                "Które ukończyłeś? (podaj numer lub fragment tekstu)"
            )
            matched2, count2 = complete_task_by_text(choice, TODO_FILE)
            if count2 == 1:
                return f"Oznaczono jako ukończone: '{matched2[0]}'"
            return f"Nie udało się jednoznacznie dopasować '{choice}' — spróbuj podać dokładniejszy fragment."

        return f"Oznaczono jako ukończone: '{matched[0]}'"

    def _reorganize_todo(self, dry_run: bool) -> str:
        effective_dry_run = dry_run or self.dry_run
        try:
            process_todo(dry_run=effective_dry_run, todo_path=TODO_FILE)
            if effective_dry_run:
                return "DRY RUN — podgląd grupowania wyświetlony w terminalu. Uruchom bez dry_run żeby zapisać."
            return "TODO.md przeorganizowane i zapisane."
        except Exception as e:
            logger.error(f"Błąd reorganizacji TODO: {e}", exc_info=True)
            return f"BŁĄD podczas reorganizacji: {e}"

    def _execute_task(self, task_text: str, agent_type: str) -> str:
        """
        Deleguje zadanie TODO do wyspecjalizowanego agenta.
        Po udanym wykonaniu oznacza zadanie jako ukończone w TODO.md.
        """
        print(f"\n🔀 Deleguję zadanie do agenta '{agent_type}': {task_text}")

        try:
            result = self._run_delegate(task_text, agent_type)
        except Exception as e:
            logger.error("Błąd delegacji zadania '%s': %s", task_text, e, exc_info=True)
            return f"BŁĄD podczas wykonywania zadania przez agenta '{agent_type}': {e}"

        if not result.success:
            return (
                f"Agent '{agent_type}' nie ukończył zadania pomyślnie.\n"
                f"Wynik: {result.output}\n"
                "Zadanie NIE zostało oznaczone jako ukończone w TODO.md."
            )

        complete_summary = self._complete_task(task_text)
        return (
            f"✅ Zadanie wykonane przez agenta '{agent_type}'.\n\n"
            f"{result.output}\n\n"
            f"TODO: {complete_summary}"
        )

    def _run_delegate(self, task_text: str, agent_type: str) -> AgentResult:
        """Inicjalizuje odpowiedniego agenta i uruchamia go z treścią zadania."""
        match agent_type:
            case "research":
                from sub_agents.research_agent import ResearchAgent
                agent = ResearchAgent(client=self.client, dry_run=self.dry_run)
                return agent.run(task_text)
            case "youtube":
                from sub_agents.youtube_agent import YoutubeAgent
                agent = YoutubeAgent(client=self.client, dry_run=self.dry_run)
                return agent.run(task_text)
            case _:
                return AgentResult(success=False, output=f"Nieznany typ agenta: '{agent_type}'")
