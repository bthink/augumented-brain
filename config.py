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
MEDIA_FILE     = VAULT_PATH / FOLDERS["ideas"]  / "Do obejrzenia i przeczytania.md"
ARCHIVE_FOLDER = VAULT_PATH / FOLDERS["archive"]

# ── TODO settings ────────────────────────────────────────────────────────────
TODO_DONE_MAX_AGE_DAYS = 30
TODO_QUICK_MAX_MINUTES = 15

# ── OpenAI ───────────────────────────────────────────────────────────────────
OPENAI_MODEL = "gpt-4o-mini"

# ── Obszary ──────────────────────────────────────────────────────────────────
# Tylko realne podfoldery w 02_Areas. "Obszary.md" jest notatką hub, nie kategorią.
AREAS = ["AI", "Money", "Photography", "Portfolio", "Praca"]

# ── Knowledge / YouTube ──────────────────────────────────────────────────────
# Foldery odzwierciedlają aktualną strukturę 03_Knowledge z vaultu.
KNOWLEDGE_FOLDERS = ["IT", "YT_summaries", "Zdrowie"]
YT_SUMMARIES_SUBFOLDER = "YT_summaries"
RESEARCH_NOTES_SUBFOLDER = "Research"

# Kategoria semantyczna -> (realny podfolder w 03_Knowledge, tytuł notatki hub)
# Model wybiera kategorię, a config mapuje ją na faktyczny folder w vaultcie.
YT_KNOWLEDGE_BY_CATEGORY: dict[str, tuple[str, str]] = {
    "ai": ("IT", "IT"),
    "it": ("IT", "IT"),
    "zdrowie": ("Zdrowie", "Zdrowie"),
    "inne": (YT_SUMMARIES_SUBFOLDER, "Yt summaries"),
}

YT_CATEGORIES = tuple(YT_KNOWLEDGE_BY_CATEGORY.keys())
YT_CATEGORY_LABELS = ", ".join(YT_CATEGORIES)
