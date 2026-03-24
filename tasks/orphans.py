"""
tasks/orphans.py — wykrywanie osieroconych notatek w vaulcie Obsidian.

Osierocona notatka = brak backlinków (żadna inna notatka jej nie linkuje).
"""

from __future__ import annotations

import re
from pathlib import Path

from config import FOLDERS, VAULT_PATH

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
SKIPPED_FOLDERS = {
    FOLDERS["inbox"],
    FOLDERS["templates"],
}


def _normalize_target(raw_target: str) -> str:
    cleaned = raw_target.strip()
    if not cleaned:
        return ""
    cleaned = cleaned.split("#", maxsplit=1)[0]
    cleaned = cleaned.split("|", maxsplit=1)[0]
    return cleaned.strip()


def _all_markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in VAULT_PATH.rglob("*.md"):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(VAULT_PATH)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in SKIPPED_FOLDERS:
            continue
        files.append(path)
    return files


def _extract_targets(content: str) -> set[str]:
    return {
        normalized
        for raw in WIKILINK_RE.findall(content)
        if (normalized := _normalize_target(raw))
    }


def find_orphan_notes() -> list[str]:
    """
    Zwraca listę osieroconych notatek (ścieżki względne względem root vaultu).
    """
    files = _all_markdown_files()
    if not files:
        return []

    stem_to_paths: dict[str, list[Path]] = {}
    for path in files:
        stem_to_paths.setdefault(path.stem, []).append(path)

    has_backlinks: set[Path] = set()
    for path in files:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for target in _extract_targets(content):
            for linked_path in stem_to_paths.get(target, []):
                if linked_path != path:
                    has_backlinks.add(linked_path)

    orphans: list[str] = []
    for path in files:
        if path in has_backlinks:
            continue
        rel = str(path.relative_to(VAULT_PATH))
        orphans.append(rel)

    return sorted(orphans, key=str.casefold)


def find_root_stray_notes() -> list[str]:
    """
    Zwraca listę plików .md leżących bezpośrednio w root vaultu (poza podfolderami PARA).
    Takie pliki nie są przypisane do żadnej kategorii i powinny trafić do Inbox lub odpowiedniego folderu.
    """
    return sorted(
        str(p.relative_to(VAULT_PATH))
        for p in VAULT_PATH.iterdir()
        if p.is_file() and p.suffix == ".md"
    )


def archive_note(relative_path: str) -> str:
    """
    Przenosi notatkę do 99_Archive i zwraca komunikat operacji.
    """
    rel_clean = str(relative_path).strip().replace("\\", "/").lstrip("/")
    if not rel_clean or ".." in rel_clean.split("/"):
        return "BŁĄD: Nieprawidłowa ścieżka notatki."

    source = (VAULT_PATH / rel_clean).resolve()
    try:
        source.relative_to(VAULT_PATH.resolve())
    except ValueError:
        return "BŁĄD: Ścieżka musi być wewnątrz vaultu."

    if not source.exists() or not source.is_file():
        return f"BŁĄD: Nie znaleziono notatki '{rel_clean}'."

    archive_dir = VAULT_PATH / FOLDERS["archive"]
    target = archive_dir / source.name
    if source == target:
        return "Notatka już jest w 99_Archive."
    if target.exists():
        return f"BŁĄD: W 99_Archive istnieje już plik '{source.name}'."

    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        source.rename(target)
    except OSError as exc:
        return f"BŁĄD: Nie udało się przenieść notatki: {exc}"

    return f"Przeniesiono '{rel_clean}' -> '99_Archive/{source.name}'"
