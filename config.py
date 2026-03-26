"""
config.py - centralna konfiguracja Augmented Brain
"""

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

# ── Ścieżka do vaultu ────────────────────────────────────────────────────────
VAULT_PATH = Path(os.environ["VAULT_PATH"])

# ── Klucz API ────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# ── Struktura PARA ───────────────────────────────────────────────────────────
FOLDERS = {
    "system":    "00_System",
    "projects":  "01_Projects",
    "areas":     "02_Areas",
    "knowledge": "03_Knowledge",
    "ideas":     "04_Ideas",
    "inbox":     "97_Inbox",
    "templates": "98_Templates",
    "archive":   "99_Archive",
}

# ── Pliki specjalne ──────────────────────────────────────────────────────────
TODO_FILE      = VAULT_PATH / FOLDERS["system"] / "TODO.md"
MEDIA_FILE     = VAULT_PATH / FOLDERS["system"] / "Do obejrzenia i przeczytania.md"
ARCHIVE_FOLDER = VAULT_PATH / FOLDERS["archive"]

# ── TODO settings ────────────────────────────────────────────────────────────
TODO_DONE_MAX_AGE_DAYS = 30
TODO_QUICK_MAX_MINUTES = 15

# ── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_MODEL = "gpt-4o-mini"

# ── Obszary ──────────────────────────────────────────────────────────────────
# Dynamicznie ładowane z 02_Areas/ przy starcie — odzwierciedla realną strukturę vaultu.
# Notatki-huby (np. "Obszary") są wykluczone z listy kategorii.
_AREAS_HUB_NOTES = {"Obszary"}


def _load_areas() -> list[str]:
    areas_dir = VAULT_PATH / FOLDERS["areas"]
    try:
        return sorted(
            p.name
            for p in areas_dir.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )
    except OSError:
        return ["AI", "Money", "Photography", "Portfolio", "Praca"]


AREAS = _load_areas()

# ── Knowledge / YouTube ──────────────────────────────────────────────────────
# Foldery odzwierciedlają aktualną strukturę 03_Knowledge z vaultu.
KNOWLEDGE_FOLDERS = ["Fotografia", "IT", "YT_summaries", "Zdrowie"]
YT_SUMMARIES_SUBFOLDER = "YT_summaries"
RESEARCH_NOTES_SUBFOLDER = "Research"

# Kategoria semantyczna -> (realny podfolder w 03_Knowledge, tytuł notatki hub)
# Model wybiera kategorię, a config mapuje ją na faktyczny folder w vaultcie.
YT_KNOWLEDGE_BY_CATEGORY: dict[str, tuple[str, str]] = {
    "ai": ("IT", "IT"),
    "it": ("IT", "IT"),
    "fotografia": ("Fotografia", "Fotografia"),
    "zdrowie": ("Zdrowie", "Zdrowie"),
    "inne": (YT_SUMMARIES_SUBFOLDER, "Yt summaries"),
}

YT_CATEGORIES = tuple(YT_KNOWLEDGE_BY_CATEGORY.keys())
YT_CATEGORY_LABELS = ", ".join(YT_CATEGORIES)
