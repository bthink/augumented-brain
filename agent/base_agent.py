"""
base_agent.py — klasa bazowa dla wszystkich sub-agentów.

Implementuje pętlę ReAct (Reason → Act → Observe) z composowalnymi skillami.
Sub-agenty dziedziczą tę klasę i deklarują swoje skille + narzędzia.
"""

import json
import logging
from typing import Any
from openai import OpenAI
from agent.skills import load_skills

logger = logging.getLogger(__name__)


class AgentResult:
    """Wynik działania agenta — przekazywany do orchestratora."""

    def __init__(self, success: bool, output: str, data: dict | None = None):
        self.success = success
        self.output = output          # czytelny dla człowieka opis co zrobiono
        self.data = data or {}        # strukturalne dane dla orchestratora


class BaseAgent:
    """
    Bazowa klasa agenta z pętlą ReAct.

    Użycie w sub-agencie:
        class InboxAgent(BaseAgent):
            SKILLS = ["clarifier", "para_classifier"]
            MAX_ITERATIONS = 8

            def get_tools(self):
                return [classify_tool, move_file_tool]
    """

    # --- konfiguracja do nadpisania w sub-agencie ---
    SKILLS: list[str] = []
    MAX_ITERATIONS: int = 10
    MODEL: str = "gpt-4o-mini"

    def __init__(self, client: OpenAI, context: dict | None = None):
        """
        Args:
            client: instancja OpenAI (przekazywana z orchestratora)
            context: dodatkowy kontekst sesji (np. ścieżki, ustawienia)
        """
        self.client = client
        self.context = context or {}
        self.skills = load_skills(self.SKILLS, self.context)
        self.tools = self.get_tools()
        self._conversation: list[dict] = []

    # ------------------------------------------------------------------
    # Metody do nadpisania w sub-agencie
    # ------------------------------------------------------------------

    def get_tools(self) -> list[dict]:
        """
        Zwraca listę narzędzi w formacie OpenAI function calling.
        Sub-agent deklaruje swoje narzędzia tutaj.
        """
        return []

    def execute_tool(self, tool_name: str, tool_args: dict) -> str:
        """
        Wykonuje narzędzie i zwraca wynik jako string.
        Sub-agent implementuje obsługę swoich narzędzi tutaj.
        """
        raise NotImplementedError(f"Narzędzie '{tool_name}' nie jest obsługiwane.")

    # ------------------------------------------------------------------
    # Pętla ReAct
    # ------------------------------------------------------------------

    def run(self, task: str) -> AgentResult:
        """
        Główna pętla agenta. Przyjmuje zadanie w języku naturalnym,
        zwraca AgentResult.
        """
        logger.info(f"[{self.__class__.__name__}] Start: {task}")
        self._conversation = []

        # Buduj system prompt ze skilli
        system_prompt = self._build_system_prompt()
        self._conversation.append({"role": "system", "content": system_prompt})
        self._conversation.append({"role": "user", "content": task})

        for iteration in range(self.MAX_ITERATIONS):
            logger.debug(f"[{self.__class__.__name__}] Iteracja {iteration + 1}")

            response = self._call_llm()
            message = response.choices[0].message

            # Agent chce wywołać narzędzie
            if message.tool_calls:
                self._conversation.append(message)
                for tool_call in message.tool_calls:
                    result = self._handle_tool_call(tool_call)
                    self._conversation.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                continue  # kolejna iteracja z wynikiem narzędzia

            # Agent skończył — zwraca finalną odpowiedź
            if message.content:
                logger.info(f"[{self.__class__.__name__}] Zakończono po {iteration + 1} iteracjach")
                return AgentResult(success=True, output=message.content)

        # Przekroczono limit iteracji
        logger.warning(f"[{self.__class__.__name__}] Przekroczono MAX_ITERATIONS={self.MAX_ITERATIONS}")
        return AgentResult(
            success=False,
            output=f"Agent przekroczył limit {self.MAX_ITERATIONS} iteracji. Zadanie może być niekompletne.",
        )

    # ------------------------------------------------------------------
    # Metody pomocnicze
    # ------------------------------------------------------------------

    def ask_user(self, question: str) -> str:
        """
        Zadaje pytanie użytkownikowi przez CLI.
        W Fazie 3 (Telegram/Slack) — nadpisz tę metodę w sub-agencie
        lub wstrzyknij inny handler przez konstruktor.
        """
        print(f"\n🤖 {question}")
        return input("Twoja odpowiedź: ").strip()

    def _build_system_prompt(self) -> str:
        """Składa system prompt ze skilli i kontekstu vaultu."""
        parts = ["Jesteś agentem systemu Augmented Brain — osobistego systemu zarządzania wiedzą."]

        for skill in self.skills:
            parts.append(f"\n## Skill: {skill['name']}\n{skill['instructions']}")

        if self.context:
            parts.append(f"\n## Kontekst sesji\n{json.dumps(self.context, ensure_ascii=False, indent=2)}")

        return "\n".join(parts)

    def _call_llm(self) -> Any:
        """Wywołuje OpenAI API z aktualną konwersacją i narzędziami."""
        kwargs: dict = {
            "model": self.MODEL,
            "messages": self._conversation,
        }
        if self.tools:
            kwargs["tools"] = self.tools
            kwargs["tool_choice"] = "auto"

        return self.client.chat.completions.create(**kwargs)

    def _handle_tool_call(self, tool_call) -> str:
        """Wywołuje narzędzie i zwraca wynik jako string."""
        tool_name = tool_call.function.name
        try:
            tool_args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return f"BŁĄD: Nieprawidłowe argumenty dla narzędzia '{tool_name}'"

        logger.info(f"[{self.__class__.__name__}] Tool: {tool_name}({tool_args})")

        try:
            result = self.execute_tool(tool_name, tool_args)
            return str(result)
        except NotImplementedError as e:
            return f"BŁĄD: {e}"
        except Exception as e:
            logger.error(f"Błąd narzędzia '{tool_name}': {e}", exc_info=True)
            return f"BŁĄD podczas wykonywania '{tool_name}': {e}"
