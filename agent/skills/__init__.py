"""
agent/skills/__init__.py — rejestr i loader skilli.

Skill to composowalny blok instrukcji + opcjonalne narzędzia.
Agent dostaje listę nazw skilli → loader składa je w jeden kontekst.
"""

from agent.skills.clarifier import SKILL as CLARIFIER
from agent.skills.para_classifier import SKILL as PARA_CLASSIFIER

# Rejestr wszystkich dostępnych skilli
# Dodaj tu nowy skill po jego stworzeniu
REGISTRY: dict[str, dict] = {
    "clarifier": CLARIFIER,
    "para_classifier": PARA_CLASSIFIER,
}


def load_skills(skill_names: list[str], context: dict) -> list[dict]:
    """
    Ładuje skille po nazwie, interpoluje kontekst w instrukcjach.

    Args:
        skill_names: lista nazw skilli do załadowania (np. ["clarifier", "para_classifier"])
        context: słownik kontekstu sesji (np. {"AREAS": ["AI", "Money", ...]})

    Returns:
        Lista słowników skill z interpolowanymi instrukcjami.

    Raises:
        ValueError: jeśli skill nie istnieje w rejestrze
    """
    loaded = []
    for name in skill_names:
        if name not in REGISTRY:
            raise ValueError(
                f"Skill '{name}' nie istnieje w rejestrze. "
                f"Dostępne: {list(REGISTRY.keys())}"
            )
        skill = REGISTRY[name].copy()

        # Interpoluj placeholdery z kontekstu (np. {AREAS})
        try:
            skill["instructions"] = skill["instructions"].format(**context)
        except KeyError:
            # Jeśli kontekst nie ma wszystkich kluczy — zostaw jak jest
            pass

        loaded.append(skill)
    return loaded


def list_skills() -> list[str]:
    """Zwraca listę nazw wszystkich dostępnych skilli."""
    return list(REGISTRY.keys())
