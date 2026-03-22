"""
sub_agents/youtube_agent.py — agent pobierający transkrypcje z YouTube i tworzący notatki w vaulcie.

Narzędzia:
    - get_yt_transcript: pobiera transkrypcję filmu
    - save_note: zapisuje notatkę w odpowiednim podfolderze 03_Knowledge wg kategorii + hub Obsidian
    - read_knowledge_note: czyta notatkę pod 03_Knowledge (ścieżka względem folderu wiedzy)
    - relocate_yt_note: przenosi istniejącą notatkę YT między podfolderami + aktualizuje kategorię/hub
    - ask_user: pyta o decyzję gdy potrzeba
"""

import json
import logging
import os
import subprocess
from pathlib import Path

from openai import OpenAI
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled

from agent.base_agent import BaseAgent, AgentResult
from agent.skills.yt_transcript import YT_TRANSCRIPT_TOOLS, fetch_transcript
from config import (
    VAULT_PATH,
    FOLDERS,
    YT_CATEGORIES,
    YT_CATEGORY_LABELS,
    YT_KNOWLEDGE_BY_CATEGORY,
    YT_SUMMARIES_SUBFOLDER,
)

logger = logging.getLogger(__name__)

YOUTUBE_TOOLS = YT_TRANSCRIPT_TOOLS + [
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": (
                "Zapisuje notatkę Markdown w vaulcie Obsidian. "
                f"Dostępne kategorie: {YT_CATEGORY_LABELS}. "
                f"Dla 'inne' domyślny folder to {YT_SUMMARIES_SUBFOLDER} + [[Yt summaries]]. "
                "System dopisze frontmatter (category) oraz właściwy [[wikilink]] hubu - "
                "w content podaj tylko treść (bez własnego --- frontmatter)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Nazwa pliku bez rozszerzenia, np. 'Rick Astley - Never Gonna Give You Up'",
                    },
                    "content": {
                        "type": "string",
                        "description": "Treść notatki Markdown (bez YAML frontmatter)",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(YT_CATEGORIES),
                        "description": "Kategoria treści filmu",
                    },
                    "folder": {
                        "type": "string",
                        "description": (
                            "Opcjonalnie: inny podfolder w 03_Knowledge niż wynika z kategorii - "
                            "tylko gdy użytkownik wyraźnie poda inną ścieżkę. Zwykle pomiń."
                        ),
                    },
                },
                "required": ["filename", "content", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_knowledge_note",
            "description": (
                "Czyta treść notatki w 03_Knowledge. Podaj ścieżkę względem tego folderu, "
                "np. 'IT/Sony A74 - Jak ustawić aparat.md' (bez vaultu od roota)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Ścieżka względem 03_Knowledge, z podfolderem i .md",
                    }
                },
                "required": ["relative_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "relocate_yt_note",
            "description": (
                "Przenosi już zapisaną notatkę YT do innego podfolderu 03_Knowledge i aktualizuje "
                f"frontmatter (category) oraz wikilink hubu zgodnie z mapowaniem kategorii ({YT_CATEGORY_LABELS}). "
                "Użyj po złej kategorii przy zapisie. Opcjonalny folder jak przy save_note (jeden segment, bez ścieżek)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Źródło względem 03_Knowledge, np. 'IT/nazwa.md'",
                    },
                    "category": {
                        "type": "string",
                        "enum": list(YT_CATEGORIES),
                        "description": "Nowa kategoria treści",
                    },
                    "folder": {
                        "type": "string",
                        "description": "Opcjonalnie inny pojedynczy podfolder niż wynika z kategorii (np. dla 'inne').",
                    },
                },
                "required": ["relative_path", "category"],
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
]


class YoutubeAgent(BaseAgent):
    SKILLS = ["yt_transcript"]
    MAX_ITERATIONS = 8
    MODEL = "gpt-4o-mini"

    def __init__(self, client: OpenAI, dry_run: bool = False):
        super().__init__(
            client=client,
            context={
                "dry_run": dry_run,
                "YT_CATEGORIES": YT_CATEGORY_LABELS,
            },
        )
        self.dry_run = dry_run
        self._knowledge_dir = VAULT_PATH / FOLDERS["knowledge"]
        self._saved_note_title: str | None = None
        self._last_action: str | None = None  # "create" | "relocate"

    def get_tools(self) -> list[dict]:
        return YOUTUBE_TOOLS

    def execute_tool(self, tool_name: str, tool_args: dict) -> str:
        match tool_name:
            case "get_yt_transcript":
                return self._get_transcript(**tool_args)
            case "save_note":
                return self._save_note(
                    tool_args["filename"],
                    tool_args["content"],
                    tool_args["category"],
                    tool_args.get("folder"),
                )
            case "read_knowledge_note":
                return self._read_knowledge_note(tool_args["relative_path"])
            case "relocate_yt_note":
                return self._relocate_yt_note(
                    tool_args["relative_path"],
                    tool_args["category"],
                    tool_args.get("folder"),
                )
            case "ask_user":
                return self.ask_user(tool_args["question"])
            case _:
                return super().execute_tool(tool_name, tool_args)

    def run(self, task: str = "") -> AgentResult:
        self._saved_note_title = None
        self._last_action = None
        if not task:
            task = "Zapytaj użytkownika o link do filmu YouTube, pobierz transkrypcję i stwórz notatkę w vaulcie."
        else:
            t_lower = task.lower()
            looks_like_fetch = any(
                x in t_lower
                for x in ("http://", "https://", "youtu.be", "youtube.com", "transkrypt")
            )
            if looks_like_fetch:
                task = (
                    f"{task}\n\n"
                    "WAŻNE: Po pobraniu transkrypcji OBOWIĄZKOWO wywołaj save_note "
                    "żeby zapisać notatkę do vaultu. Nie kończ bez zapisania notatki."
                )
        result = super().run(task)
        if result.success and self._saved_note_title:
            label = self._saved_note_title
            if self._last_action == "relocate":
                if self.dry_run:
                    msg = f"[DRY RUN] Notatka „{label}” zostałaby przeniesiona."
                else:
                    msg = f'Notatka „{label}” została przeniesiona.'
            elif self.dry_run:
                msg = f"[DRY RUN] Notatka „{label}” zostałaby utworzona."
            else:
                msg = f'Notatka „{label}” została utworzona.'
            return AgentResult(success=True, output=msg)
        return result

    # ------------------------------------------------------------------
    # Implementacje narzędzi
    # ------------------------------------------------------------------

    def _get_transcript(self, url: str, lang: str = "pl,en", include_meta: bool = False) -> str:
        try:
            result = fetch_transcript(url, lang=lang, include_meta=include_meta)
            return json.dumps(result, ensure_ascii=False)
        except ValueError as e:
            return f"BŁĄD: {e}"
        except TranscriptsDisabled:
            return "BŁĄD: Transkrypcje są wyłączone dla tego filmu."
        except NoTranscriptFound:
            return f"BŁĄD: Nie znaleziono transkrypcji w językach: {lang}"
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas pobierania transkrypcji: {e}", exc_info=True)
            return f"BŁĄD: {e}"

    def _path_under_knowledge(self, relative: str) -> Path | None:
        rel = str(relative).strip().replace("\\", "/").lstrip("/")
        if not rel or any(part == ".." for part in rel.split("/")):
            return None
        p = (self._knowledge_dir / rel).resolve()
        kd = self._knowledge_dir.resolve()
        try:
            p.relative_to(kd)
        except ValueError:
            return None
        return p

    @staticmethod
    def _strip_yt_body_from_note(raw: str) -> str:
        t = raw.strip()
        if t.startswith("---"):
            end = t.find("\n---", 3)
            if end != -1:
                t = t[end + 4 :].lstrip()
        lines = t.splitlines()
        if lines and lines[0].strip().startswith("[[") and "]]" in lines[0]:
            t = "\n".join(lines[1:]).lstrip()
        return t

    def _obsidian_move(self, source: Path, target: Path) -> bool:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["obsidian", "move", str(source), str(target)],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("Obsidian CLI: przeniesiono %s", source.name)
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.debug("Obsidian CLI niedostępne — używam os.rename")

        try:
            os.rename(source, target)
            return True
        except OSError as e:
            logger.error("Błąd przenoszenia: %s", e, exc_info=True)
            return False

    def _read_knowledge_note(self, relative_path: str) -> str:
        p = self._path_under_knowledge(relative_path)
        if not p:
            return "BŁĄD: Nieprawidłowa ścieżka względem 03_Knowledge."
        if not p.is_file():
            return f"BŁĄD: Brak pliku: {relative_path}"
        try:
            content = p.read_text(encoding="utf-8").strip()
        except OSError as e:
            return f"BŁĄD odczytu: {e}"
        if len(content) > 12000:
            return content[:12000] + "\n\n[... skrócono ...]"
        return content

    def _relocate_yt_note(
        self,
        relative_path: str,
        category: str,
        folder_override: str | None,
    ) -> str:
        if category not in YT_KNOWLEDGE_BY_CATEGORY:
            return (
                f"BŁĄD: Nieprawidłowa kategoria „{category}”. "
                f"Dozwolone: {', '.join(YT_CATEGORIES)}."
            )

        source = self._path_under_knowledge(relative_path)
        if not source:
            return "BŁĄD: Nieprawidłowa ścieżka względem 03_Knowledge."
        if not source.is_file():
            return f"BŁĄD: Brak pliku: {relative_path}"

        sub, sub_err = self._resolve_subfolder(category, folder_override)
        if sub_err:
            return sub_err

        note_dir = self._knowledge_dir / sub
        target = note_dir / source.name

        if target.exists() and target.resolve() != source.resolve():
            return f"BŁĄD: Istnieje już plik docelowy: {sub}/{source.name}"

        try:
            raw = source.read_text(encoding="utf-8")
        except OSError as e:
            return f"BŁĄD odczytu: {e}"

        body = self._strip_yt_body_from_note(raw)
        full_text = self._finalize_yt_note_content(body, category)
        rel_display = f"{FOLDERS['knowledge']}/{sub}"

        if self.dry_run:
            self._saved_note_title = f"{sub}/{source.name}"
            self._last_action = "relocate"
            return (
                f"[DRY RUN] Przeniósłbym „{source.name}” → {rel_display}/ "
                f"(kategoria: {category})"
            )

        if not self._knowledge_dir.exists():
            return f"BŁĄD: Folder {self._knowledge_dir} nie istnieje."

        try:
            note_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return f"BŁĄD: nie można utworzyć folderu {note_dir}: {e}"

        try:
            source.write_text(full_text, encoding="utf-8")
        except OSError as e:
            return f"BŁĄD zapisu treści: {e}"

        if source.resolve() == target.resolve():
            self._saved_note_title = f"{sub}/{source.name}"
            self._last_action = "relocate"
            return f"Zaktualizowano notatkę: {rel_display}/{source.name}"

        if self._obsidian_move(source, target):
            self._saved_note_title = f"{sub}/{source.name}"
            self._last_action = "relocate"
            return f"Przeniesiono i zaktualizowano: {rel_display}/{source.name}"
        return "BŁĄD: nie udało się przenieść pliku (Obsidian CLI / rename)."

    @staticmethod
    def _resolve_subfolder(category: str, folder_override: str | None) -> tuple[str, str | None]:
        """
        Zwraca (podfolder, komunikat_błędu).
        Domyślnie podfolder z YT_KNOWLEDGE_BY_CATEGORY; override tylko przy jawnej prośbie użytkownika.
        """
        default_sub, _ = YT_KNOWLEDGE_BY_CATEGORY[category]
        if not folder_override or not str(folder_override).strip():
            return default_sub, None
        s = str(folder_override).strip().strip("/\\")
        if not s or ".." in s or "/" in s or "\\" in s:
            return default_sub, (
                f"BŁĄD: Nieprawidłowa nazwa folderu „{folder_override}”. "
                f"Użyj jednego segmentu bez ścieżek (np. {YT_SUMMARIES_SUBFOLDER})."
            )
        return s, None

    @staticmethod
    def _finalize_yt_note_content(content: str, category: str) -> str:
        _, hub_title = YT_KNOWLEDGE_BY_CATEGORY[category]
        body = (content or "").strip()
        return (
            "---\n"
            f"category: {category}\n"
            "---\n\n"
            f"[[{hub_title}]]\n\n"
            f"{body}"
        )

    def _save_note(
        self,
        filename: str,
        content: str,
        category: str,
        folder: str | None = None,
    ) -> str:
        if category not in YT_KNOWLEDGE_BY_CATEGORY:
            return (
                f"BŁĄD: Nieprawidłowa kategoria „{category}”. "
                f"Dozwolone: {', '.join(YT_CATEGORIES)}."
            )

        safe_name = "".join(c for c in filename if c not in r'\/:*?"<>|').strip()
        if not safe_name:
            return "BŁĄD: Nieprawidłowa nazwa pliku."

        note_title = f"{safe_name}.md"
        sub, sub_err = self._resolve_subfolder(category, folder)
        if sub_err:
            return sub_err
        note_dir = self._knowledge_dir / sub
        full_text = self._finalize_yt_note_content(content, category)
        rel_display = f"{FOLDERS['knowledge']}/{sub}"

        if self.dry_run:
            self._saved_note_title = f"{sub}/{note_title}"
            self._last_action = "create"
            return (
                f"[DRY RUN] Symulacja zapisu notatki „{note_title}” do {rel_display} - OK."
            )

        if not self._knowledge_dir.exists():
            return f"BŁĄD: Folder {self._knowledge_dir} nie istnieje."

        try:
            note_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Nie można utworzyć folderu {note_dir}: {e}", exc_info=True)
            return f"BŁĄD: nie można utworzyć folderu {note_dir}: {e}"

        target = note_dir / note_title

        if target.exists():
            return (
                f"BŁĄD: Plik '{target.name}' już istnieje. "
                "Wybierz inną nazwę lub potwierdź nadpisanie."
            )

        try:
            target.write_text(full_text, encoding="utf-8")
            self._saved_note_title = f"{sub}/{note_title}"
            self._last_action = "create"
            logger.info(f"Zapisano notatkę: {target}")
            return f"Zapisano notatkę: {rel_display}/{target.name}"
        except OSError as e:
            logger.error(f"Błąd zapisu pliku {target}: {e}", exc_info=True)
            return f"BŁĄD podczas zapisu: {e}"
