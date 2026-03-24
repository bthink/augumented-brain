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
from sub_agents.orphans_agent import OrphansAgent
from sub_agents.research_agent import ResearchAgent
from sub_agents.todo_agent import TodoAgent
from sub_agents.youtube_agent import YoutubeAgent
from config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

# Mapa komend → sub-agentów (rozszerz gdy dodajesz nowe)
AGENT_DESCRIPTIONS = {
    "inbox": "WYŁĄCZNIE pliki w 97_Inbox/ — klasyfikacja PARA i przeniesienie stamtąd. "
    "Nie używaj, gdy chodzi o notatkę już w 03_Knowledge lub innym folderze niż Inbox.",
    "todo": "Organizuje zadania w TODO.md — grupuje i czyści ukończone",
    "youtube": "Transkrypcja YouTube i zapis notatki w 03_Knowledge. "
    "Także: przeniesienie lub zmiana kategorii istniejącej notatki YT już w 03_Knowledge (np. zła kategoria/podfolder).",
    "research": (
        "Odpowiada na pytania wymagające wiedzy z vaultu lub internetu. "
        "Używaj gdy: użytkownik pyta o coś co może być w notatce, chce przeczytać notatkę i dowiedzieć się więcej, "
        "prosi o research tematu, chce połączyć wiedzę z vaultu z informacjami z sieci. "
        "Agent może zapisać notatkę, ale nie musi — zależy od prośby."
    ),
    "orphans": "Znajduje osierocone notatki (bez backlinków) i opcjonalnie przenosi je do 99_Archive.",
}


class Orchestrator:
    """
    Router komend do odpowiednich sub-agentów.

    Użycie:
        orch = Orchestrator()
        result = orch.run("ogarnij inbox i pokaż co tam masz")
    """

    def __init__(self, dry_run: bool = False):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.dry_run = dry_run
        self.last_agent: str | None = None

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
            else:
                self.last_agent = agent_name

        return "\n\n".join(results)

    def _plan(self, user_input: str) -> list[str]:
        """
        Pyta LLM który sub-agent wywołać.
        Zwraca listę nazw agentów w kolejności wykonania.
        """
        descriptions = "\n".join(
            f"- {name}: {desc}" for name, desc in AGENT_DESCRIPTIONS.items()
        )

        last_agent_hint = (
            f"\nOstatni użyty agent: {self.last_agent}. "
            "Jeśli polecenie jest krótkie, kontynuuje poprzedni temat lub jest odpowiedzią "
            "(np. 'tak', 'nie', 'ok', numer), użyj tego samego agenta."
            if self.last_agent
            else ""
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
                        "Zasady:\n"
                        "- inbox: TYLKO pliki w 97_Inbox, nigdy dla notatek już w vault\n"
                        "- youtube: przenieś/popraw notatkę YT w 03_Knowledge lub transkrypcja\n"
                        "- research: pytania o notatki w vaulcie, pytania ogólne, research z/bez zapisu\n"
                        "- orphans: analiza osieroconych notatek i porządki archiwalne\n"
                        "- jeśli nie pasuje nic innego, użyj research\n"
                        "Odpowiedz TYLKO nazwami, np: inbox,todo\n"
                        "Jeśli jakaś funkcja jest niedostępna, napisz: UNAVAILABLE"
                        f"{last_agent_hint}"
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
            if self.last_agent:
                logger.warning(
                    "Router nie wskazał agenta — fallback do ostatniego: %s", self.last_agent
                )
                return [self.last_agent]
            logger.warning("Router nie wskazał agenta — fallback: research")
            return ["research"]

        agents = [name.strip() for name in raw.split(",") if name.strip() in AGENT_DESCRIPTIONS]
        if not agents:
            if self.last_agent:
                logger.warning(
                    "Router zwrócił nieznane nazwy ('%s') — fallback do ostatniego: %s",
                    raw,
                    self.last_agent,
                )
                return [self.last_agent]
            logger.warning("Router zwrócił nieznane nazwy ('%s') — fallback: research", raw)
            return ["research"]
        return agents

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
            case "research":
                agent = ResearchAgent(client=self.client, dry_run=self.dry_run)
                return agent.run(task)
            case "orphans":
                agent = OrphansAgent(client=self.client, dry_run=self.dry_run)
                return agent.run(task)
            case _:
                from agent.base_agent import AgentResult
                return AgentResult(False, f"Nieznany agent: {agent_name}")
