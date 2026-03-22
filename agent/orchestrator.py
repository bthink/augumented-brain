"""
agent/orchestrator.py — główny orkiestrator systemu.

Przyjmuje polecenie użytkownika w języku naturalnym,
decyduje który sub-agent wywołać i w jakiej kolejności,
zbiera wyniki i zwraca podsumowanie.

Na razie: prosty router oparty o LLM.
W przyszłości: pełna pętla ReAct na poziomie orchestratora.
"""

import logging
from openai import OpenAI

from sub_agents.inbox_agent import InboxAgent
from sub_agents.todo_agent import TodoAgent
from sub_agents.youtube_agent import YoutubeAgent
from config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

# Mapa komend → sub-agentów (rozszerz gdy dodajesz nowe)
AGENT_DESCRIPTIONS = {
    "inbox": "Przetwarza notatki z 97_Inbox/ — klasyfikuje i przenosi do PARA",
    "todo": "Organizuje zadania w TODO.md — grupuje i czyści ukończone",
    "youtube": "Pobiera transkrypcję filmu z YouTube i tworzy notatkę w 03_Knowledge vaultu",
    "research": "Prowadzi research na podany temat — łączy vault z internetem [wkrótce]",
    "orphans": "Znajduje notatki bez linków — kandydaci do archiwum [wkrótce]",
}


class Orchestrator:
    """
    Router komend do odpowiednich sub-agentów.

    Użycie:
        orch = Orchestrator()
        result = orch.run("ogarnij inbox i pokaż co tam masz")
    """

    def __init__(self, dry_run: bool = True):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.dry_run = dry_run

    def run(self, user_input: str) -> str:
        """
        Główna metoda. Przyjmuje komendę, zwraca raport jako string.
        """
        print(f"\n🧠 Orchestrator: analizuję '{user_input}'")

        # Zdecyduj który agent(y) wywołać
        plan = self._plan(user_input)
        print(f"📋 Plan: {plan}")

        results = []
        for agent_name in plan:
            print(f"\n▶️  Uruchamiam: {agent_name}")
            result = self._run_agent(agent_name, user_input)
            results.append(f"### {agent_name}\n{result.output}")
            if not result.success:
                print(f"⚠️  {agent_name} zakończył z błędem")

        return "\n\n".join(results)

    def _plan(self, user_input: str) -> list[str]:
        """
        Pyta LLM który sub-agent wywołać.
        Zwraca listę nazw agentów w kolejności wykonania.
        """
        descriptions = "\n".join(
            f"- {name}: {desc}" for name, desc in AGENT_DESCRIPTIONS.items()
        )

        response = self.client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Jesteś routerem komend. Na podstawie polecenia użytkownika "
                        "zwróć TYLKO listę nazw agentów do wywołania, oddzielonych przecinkami.\n"
                        f"Dostępne agenty:\n{descriptions}\n\n"
                        "Odpowiedz TYLKO nazwami, np: inbox,todo\n"
                        "Jeśli agent jest oznaczony [wkrótce] — nie używaj go, "
                        "zamiast tego napisz: UNAVAILABLE"
                    ),
                },
                {"role": "user", "content": user_input},
            ],
            max_tokens=50,
        )

        raw = response.choices[0].message.content.strip().lower()

        if "unavailable" in raw:
            print("⚠️  Część funkcji jest jeszcze niedostępna")
            raw = raw.replace("unavailable", "").strip(",").strip()

        if not raw:
            return []

        return [name.strip() for name in raw.split(",") if name.strip() in AGENT_DESCRIPTIONS]

    def _run_agent(self, agent_name: str, task: str):
        """Inicjalizuje i uruchamia odpowiedni sub-agent."""
        match agent_name:
            case "inbox":
                agent = InboxAgent(client=self.client, dry_run=self.dry_run)
                return agent.run()
            case "todo":
                agent = TodoAgent(client=self.client, dry_run=self.dry_run)
                return agent.run(task)
            case "youtube":
                agent = YoutubeAgent(client=self.client, dry_run=self.dry_run)
                return agent.run(task)
            case _:
                from agent.base_agent import AgentResult
                return AgentResult(False, f"Nieznany agent: {agent_name}")