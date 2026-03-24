"""
tasks/moc.py — aktualizacja notatek hub (Map of Content) w vaulcie Obsidian.

Notatka hub = plik .md zbierający wikilinki do notatek w danym temacie,
np. 03_Knowledge/IT.md agreguje linki do notatek w 03_Knowledge/IT/.

Funkcja update_hub_note() jest wywoływana przez YoutubeAgent i ResearchAgent
po każdym zapisie nowej notatki — nie przez użytkownika bezpośrednio.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def update_hub_note(hub_path: Path, new_note_title: str, dry_run: bool = False) -> str:
    """
    Dodaje wikilink [[new_note_title]] do pliku hub_path.

    Jeśli hub nie istnieje — tworzy go z nagłówkiem i pierwszym wikilinkiem.
    Jeśli wikilink już jest w pliku — pomija bez błędu.
    Zwraca komunikat operacji (zawsze str, nigdy nie rzuca wyjątku).
    """
    wikilink = f"[[{new_note_title}]]"

    if dry_run:
        try:
            if hub_path.is_file():
                content = hub_path.read_text(encoding="utf-8")
                if wikilink in content:
                    return f"[DRY RUN] {wikilink} już istnieje w {hub_path.name} — brak zmian."
            return f"[DRY RUN] Dodałbym {wikilink} do {hub_path.name}."
        except OSError as e:
            return f"[DRY RUN] Nie można odczytać {hub_path.name}: {e}"

    try:
        if hub_path.is_file():
            content = hub_path.read_text(encoding="utf-8")
            if wikilink in content:
                logger.debug("MOC: %s już zawiera %s", hub_path.name, wikilink)
                return f"Wikilink {wikilink} już istnieje w {hub_path.name}."
            updated = content.rstrip() + f"\n{wikilink}\n"
            hub_path.write_text(updated, encoding="utf-8")
            logger.info("MOC: dodano %s do %s", wikilink, hub_path.name)
            return f"Dodano {wikilink} do {hub_path.name}."
        else:
            hub_path.parent.mkdir(parents=True, exist_ok=True)
            hub_path.write_text(
                f"# {hub_path.stem}\n\n{wikilink}\n",
                encoding="utf-8",
            )
            logger.info("MOC: utworzono hub %s z %s", hub_path.name, wikilink)
            return f"Utworzono hub {hub_path.name} z {wikilink}."
    except OSError as e:
        logger.error("Błąd MOC update %s: %s", hub_path, e, exc_info=True)
        return f"BŁĄD MOC update: {e}"
