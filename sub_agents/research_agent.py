"""
sub_agents/research_agent.py - agent do researchu łączącego vault i internet.

Narzędzia:
    - search_web: wyszukiwanie w sieci
    - read_webpage: pobranie i uproszczony odczyt strony
    - search_vault: wyszukiwanie istniejących notatek w vaulcie
    - read_vault_note: odczyt konkretnej notatki z vaultu
    - save_research_note: zapis gotowej notatki do 03_Knowledge
    - ask_user: pytanie doprecyzowujące
"""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import subprocess
from datetime import date
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai import OpenAI

from agent.base_agent import BaseAgent, AgentResult
from config import AREAS, FOLDERS, RESEARCH_NOTES_SUBFOLDER, VAULT_PATH

try:
    import certifi
except ImportError:
    certifi = None

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; AugmentedBrain/1.0; +https://github.com/bthink/augumented-brain)"
MAX_PAGE_CHARS = 15000
MAX_NOTE_CHARS = 12000

RESEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Wyszukuje strony WWW dla zadanego zapytania i zwraca listę wyników "
                "z tytułem, URL i krótkim snippetem."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Fraza do wyszukania w sieci",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maksymalna liczba wyników, domyślnie 5",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": (
                "Pobiera stronę WWW i zwraca uproszczony tekst, tytuł oraz URL końcowy. "
                "Używaj po search_web, zanim wyciągniesz wnioski."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Pełny URL strony do przeczytania",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_vault",
            "description": (
                "Przeszukuje markdowny w vaulcie po nazwie pliku i treści. "
                "Używaj przed tworzeniem nowej notatki, żeby znaleźć istniejący kontekst."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Fraza do wyszukania w vaulcie",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maksymalna liczba wyników, domyślnie 8",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_vault_note",
            "description": (
                "Czyta notatkę markdown z vaultu. Podaj ścieżkę względną od root vaultu, "
                "np. '03_Knowledge/Research/temat.md'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Ścieżka względna od root vaultu",
                    }
                },
                "required": ["relative_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_research_note",
            "description": (
                "Zapisuje notatkę researchową do 03_Knowledge. "
                "Domyślny podfolder to Research, chyba że użytkownik jawnie poda inny folder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Nazwa pliku bez rozszerzenia .md",
                    },
                    "content": {
                        "type": "string",
                        "description": "Treść notatki Markdown bez frontmatter",
                    },
                    "folder": {
                        "type": "string",
                        "description": (
                            "Opcjonalny pojedynczy podfolder w 03_Knowledge, "
                            "np. 'AI' lub 'Research'."
                        ),
                    },
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_vault_note",
            "description": (
                "Przenosi notatkę między folderami vaultu i aktualizuje wikilinki (Obsidian CLI). "
                "Używaj gdy użytkownik prosi o przeniesienie już istniejącej notatki do innego miejsca, "
                f"np. do 02_Areas/Photography lub 03_Knowledge/IT. Dostępne obszary: {AREAS}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source_path": {
                        "type": "string",
                        "description": "Ścieżka źródłowa względem root vaultu, np. '03_Knowledge/Research/Temat.md'",
                    },
                    "target_folder": {
                        "type": "string",
                        "description": (
                            "Folder docelowy względem root vaultu (bez nazwy pliku), "
                            "np. '02_Areas/Photography' lub '03_Knowledge/IT'"
                        ),
                    },
                },
                "required": ["source_path", "target_folder"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Zadaje użytkownikowi pytanie i czeka na odpowiedź.",
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


def _clean_html(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)</div>|</li>|</section>|</article>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _extract_title(html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip() if match else ""


def _resolve_duckduckgo_url(raw_url: str) -> str:
    if raw_url.startswith("//"):
        return f"https:{raw_url}"
    if "duckduckgo.com/l/?" not in raw_url:
        return raw_url
    parsed = urlparse(raw_url)
    query = parse_qs(parsed.query)
    uddg = query.get("uddg", [""])[0]
    return unquote(uddg) if uddg else raw_url


def _safe_relative_path(relative_path: str) -> Path | None:
    rel = str(relative_path).strip().replace("\\", "/").lstrip("/")
    if not rel or any(part == ".." for part in rel.split("/")):
        return None
    path = (VAULT_PATH / rel).resolve()
    try:
        path.relative_to(VAULT_PATH.resolve())
    except ValueError:
        return None
    return path


def _build_ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


class ResearchAgent(BaseAgent):
    SKILLS = ["clarifier", "web_analyst"]
    MAX_ITERATIONS = 12
    MODEL = "gpt-4o-mini"

    def __init__(self, client: OpenAI, dry_run: bool = False):
        super().__init__(
            client=client,
            context={
                "dry_run": dry_run,
                "knowledge_folder": FOLDERS["knowledge"],
                "default_research_subfolder": RESEARCH_NOTES_SUBFOLDER,
            },
        )
        self.dry_run = dry_run
        self._knowledge_dir = VAULT_PATH / FOLDERS["knowledge"]
        self._saved_note_title: str | None = None

    def get_tools(self) -> list[dict]:
        return RESEARCH_TOOLS

    def execute_tool(self, tool_name: str, tool_args: dict) -> str:
        match tool_name:
            case "search_web":
                return self._search_web(tool_args["query"], tool_args.get("max_results", 5))
            case "read_webpage":
                return self._read_webpage(tool_args["url"])
            case "search_vault":
                return self._search_vault(tool_args["query"], tool_args.get("max_results", 8))
            case "read_vault_note":
                return self._read_vault_note(tool_args["relative_path"])
            case "save_research_note":
                return self._save_research_note(
                    tool_args["filename"],
                    tool_args["content"],
                    tool_args.get("folder"),
                )
            case "move_vault_note":
                return self._move_vault_note(
                    tool_args["source_path"],
                    tool_args["target_folder"],
                )
            case "ask_user":
                return self.ask_user(tool_args["question"])
            case _:
                return super().execute_tool(tool_name, tool_args)

    def run(self, task: str = "") -> AgentResult:
        self._saved_note_title = None
        if not task:
            task = (
                "Zrób research na wskazany temat. "
                "Najpierw oceń, czy wystarczy wiedza modelu lub istniejące notatki z vaultu. "
                "Po źródła z sieci sięgaj tylko wtedy, gdy potrzebujesz weryfikacji, aktualności albo linków. "
                "Na końcu zapisz notatkę researchową."
            )
        else:
            task = (
                f"{task}\n\n"
                "WAŻNE:\n"
                "1. Jeśli zadanie to przeniesienie notatki — użyj move_vault_note i zakończ.\n"
                "2. Jeśli zadanie to pytanie lub research — najpierw oceń, czy wystarczy wiedza modelu.\n"
                "3. Jeśli temat może już istnieć w notatkach, użyj search_vault.\n"
                "4. Użyj search_web i read_webpage tylko gdy potrzebujesz aktualności lub zewnętrznej weryfikacji.\n"
                "5. Dla research: zapisz wynik przez save_research_note, chyba że użytkownik prosi tylko o odpowiedź.\n"
            )

        result = super().run(task)
        if result.success and self._saved_note_title:
            if self.dry_run:
                msg = f"[DRY RUN] Notatka researchowa '{self._saved_note_title}' zostałaby utworzona."
            else:
                msg = f"Notatka researchowa '{self._saved_note_title}' została utworzona."
            return AgentResult(success=True, output=msg)
        return result

    def _fetch_text(self, url: str) -> tuple[str, str]:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=15, context=_build_ssl_context()) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
            raw = response.read().decode(charset, errors="replace")
            return final_url, raw

    def _search_web(self, query: str, max_results: int = 5) -> str:
        query = query.strip()
        if not query:
            return "BŁĄD: Puste zapytanie."
        limit = min(max(int(max_results or 5), 1), 10)
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"

        try:
            _, html = self._fetch_text(url)
        except HTTPError as e:
            logger.warning("search_web HTTPError for %s: %s", query, e)
            return f"BŁĄD: Wyszukiwarka zwróciła HTTP {e.code}."
        except URLError as e:
            if isinstance(e.reason, ssl.SSLError):
                logger.warning("search_web TLS error for %s: %s", query, e.reason)
                return (
                    "BŁĄD: Problem z weryfikacją TLS/SSL przy połączeniu z wyszukiwarką. "
                    "Sprawdź certyfikaty systemowe lub instalację certifi."
                )
            logger.warning("search_web URLError for %s: %s", query, e)
            return (
                "BŁĄD: Nie udało się połączyć z wyszukiwarką. "
                f"Szczegóły: {e.reason}"
            )
        except Exception as e:
            logger.warning("search_web unexpected error for %s: %s", query, e)
            return f"BŁĄD: Nie udało się wykonać wyszukiwania: {e}"

        pattern = re.compile(
            r'(?is)<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
            r'(?:.*?<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|.*?<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>)?'
        )
        results = []
        for match in pattern.finditer(html):
            raw_url = match.group(1)
            title = _clean_html(match.group(2))
            snippet = _clean_html(match.group(3) or match.group(4) or "")
            resolved = _resolve_duckduckgo_url(raw_url)
            if not title or not resolved.startswith(("http://", "https://")):
                continue
            if any(r["url"] == resolved for r in results):
                continue
            results.append({"title": title, "url": resolved, "snippet": snippet})
            if len(results) >= limit:
                break

        if not results:
            return "Brak wyników."
        return json.dumps(results, ensure_ascii=False)

    def _read_webpage(self, url: str) -> str:
        if not str(url).startswith(("http://", "https://")):
            return "BŁĄD: URL musi zaczynać się od http:// lub https://"
        try:
            final_url, html = self._fetch_text(url)
        except HTTPError as e:
            logger.warning("read_webpage HTTPError for %s: %s", url, e)
            return f"BŁĄD: Strona zwróciła HTTP {e.code}."
        except URLError as e:
            if isinstance(e.reason, ssl.SSLError):
                logger.warning("read_webpage TLS error for %s: %s", url, e.reason)
                return (
                    "BŁĄD: Problem z weryfikacją TLS/SSL przy pobieraniu strony. "
                    "Sprawdź certyfikaty systemowe lub instalację certifi."
                )
            logger.warning("read_webpage URLError for %s: %s", url, e)
            return f"BŁĄD: Nie udało się połączyć ze stroną. Szczegóły: {e.reason}"
        except Exception as e:
            logger.warning("read_webpage unexpected error for %s: %s", url, e)
            return f"BŁĄD: Nie udało się pobrać strony: {e}"

        title = _extract_title(html)
        text = _clean_html(html)
        if len(text) > MAX_PAGE_CHARS:
            text = text[:MAX_PAGE_CHARS] + "\n\n[... skrócono ...]"

        return json.dumps(
            {
                "title": title,
                "url": final_url,
                "content": text,
            },
            ensure_ascii=False,
        )

    def _search_vault(self, query: str, max_results: int = 8) -> str:
        phrase = query.strip().lower()
        if not phrase:
            return "BŁĄD: Puste zapytanie."

        limit = min(max(int(max_results or 8), 1), 20)
        results = []

        for path in VAULT_PATH.rglob("*.md"):
            if not path.is_file():
                continue
            try:
                raw = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel = str(path.relative_to(VAULT_PATH))
            haystack = f"{path.stem}\n{raw}".lower()
            if phrase not in haystack:
                continue

            idx = haystack.find(phrase)
            snippet_start = max(idx - 120, 0)
            snippet_end = min(idx + 240, len(raw))
            snippet = raw[snippet_start:snippet_end].replace("\n", " ").strip()

            results.append(
                {
                    "path": rel,
                    "title": path.stem,
                    "snippet": re.sub(r"\s{2,}", " ", snippet),
                }
            )
            if len(results) >= limit:
                break

        if not results:
            return "Brak wyników."
        return json.dumps(results, ensure_ascii=False)

    def _read_vault_note(self, relative_path: str) -> str:
        path = _safe_relative_path(relative_path)
        if not path:
            return "BŁĄD: Nieprawidłowa ścieżka."
        if not path.is_file():
            return f"BŁĄD: Brak pliku: {relative_path}"
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            return f"BŁĄD odczytu: {e}"

        if len(content) > MAX_NOTE_CHARS:
            content = content[:MAX_NOTE_CHARS] + "\n\n[... skrócono ...]"
        return content

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
            logger.error("Błąd przenoszenia %s → %s: %s", source, target, e, exc_info=True)
            return False

    def _move_vault_note(self, source_path: str, target_folder: str) -> str:
        source = _safe_relative_path(source_path)
        if not source:
            return "BŁĄD: Nieprawidłowa ścieżka źródłowa."
        if not source.is_file():
            return f"BŁĄD: Plik nie istnieje: {source_path}"

        target_folder_clean = str(target_folder).strip().replace("\\", "/").strip("/")
        if not target_folder_clean or ".." in target_folder_clean.split("/"):
            return "BŁĄD: Nieprawidłowy folder docelowy."

        target_dir = (VAULT_PATH / target_folder_clean).resolve()
        try:
            target_dir.relative_to(VAULT_PATH.resolve())
        except ValueError:
            return "BŁĄD: Folder docelowy musi być wewnątrz vaultu."

        target = target_dir / source.name
        if target.resolve() == source.resolve():
            return f"Notatka już jest w {target_folder_clean}/."

        if self.dry_run:
            return f"[DRY RUN] Przeniósłbym '{source.name}' → {target_folder_clean}/"

        if target.exists():
            return f"BŁĄD: Plik '{source.name}' już istnieje w {target_folder_clean}/."

        if self._obsidian_move(source, target):
            logger.info("Przeniesiono %s → %s", source_path, target_folder_clean)
            return f"Przeniesiono '{source.name}' → {target_folder_clean}/"
        return "BŁĄD: Nie udało się przenieść pliku."

    def _save_research_note(self, filename: str, content: str, folder: str | None = None) -> str:
        safe_name = "".join(c for c in filename if c not in r'\/:*?"<>|').strip()
        if not safe_name:
            return "BŁĄD: Nieprawidłowa nazwa pliku."

        if folder and any(x in str(folder) for x in ("..", "/", "\\")):
            return "BŁĄD: Folder musi być pojedynczym segmentem."

        subfolder = (folder or RESEARCH_NOTES_SUBFOLDER).strip() or RESEARCH_NOTES_SUBFOLDER
        note_dir = self._knowledge_dir / subfolder
        note_path = note_dir / f"{safe_name}.md"

        frontmatter = (
            "---\n"
            "type: research\n"
            f"date: {date.today().isoformat()}\n"
            "---\n\n"
        )
        full_text = frontmatter + content.strip() + "\n"

        if self.dry_run:
            self._saved_note_title = f"{subfolder}/{safe_name}.md"
            return f"[DRY RUN] Zapisałbym notatkę do {FOLDERS['knowledge']}/{subfolder}/{safe_name}.md"

        if note_path.exists():
            return f"BŁĄD: Plik '{note_path.name}' już istnieje."

        try:
            note_dir.mkdir(parents=True, exist_ok=True)
            note_path.write_text(full_text, encoding="utf-8")
        except OSError as e:
            logger.error("Błąd zapisu research note %s: %s", note_path, e)
            return f"BŁĄD zapisu: {e}"

        self._saved_note_title = f"{subfolder}/{safe_name}.md"
        return f"Zapisano notatkę: {FOLDERS['knowledge']}/{subfolder}/{safe_name}.md"
