"""
tasks/web_utils.py — wspólne narzędzia HTTP/web dla sub-agentów.

Funkcje search_web i read_webpage zwracają JSON (string), co ułatwia
użycie ich jako tool-result w pętli ReAct.
"""

from __future__ import annotations

import json
import logging
import re
import ssl
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:
    certifi = None

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; AugmentedBrain/1.0; "
    "+https://github.com/bthink/augumented-brain)"
)
DEFAULT_MAX_PAGE_CHARS = 15_000


def _build_ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


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


def fetch_page(url: str) -> tuple[str, str]:
    """Pobiera stronę HTTP(S). Zwraca (final_url, html_content)."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=15, context=_build_ssl_context()) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        final_url = response.geturl()
        raw = response.read().decode(charset, errors="replace")
        return final_url, raw


def search_web(query: str, max_results: int = 5) -> str:
    """Wyszukuje przez DuckDuckGo. Zwraca JSON z listą wyników lub komunikat błędu."""
    query = query.strip()
    if not query:
        return "BŁĄD: Puste zapytanie."

    limit = min(max(int(max_results or 5), 1), 10)
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"

    try:
        _, html = fetch_page(url)
    except HTTPError as e:
        logger.warning("search_web HTTPError for %s: %s", query, e)
        return f"BŁĄD: Wyszukiwarka zwróciła HTTP {e.code}."
    except URLError as e:
        if isinstance(e.reason, ssl.SSLError):
            logger.warning("search_web TLS error for %s: %s", query, e.reason)
            return "BŁĄD: Problem z TLS/SSL. Sprawdź certyfikaty lub instalację certifi."
        logger.warning("search_web URLError for %s: %s", query, e)
        return f"BŁĄD: Nie udało się połączyć z wyszukiwarką. Szczegóły: {e.reason}"
    except Exception as e:
        logger.warning("search_web unexpected error for %s: %s", query, e)
        return f"BŁĄD: Nie udało się wykonać wyszukiwania: {e}"

    pattern = re.compile(
        r'(?is)<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'(?:.*?<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>'
        r'|.*?<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>)?'
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


def read_webpage(url: str, max_chars: int = DEFAULT_MAX_PAGE_CHARS) -> str:
    """Pobiera stronę i zwraca JSON {title, url, content} lub komunikat błędu."""
    if not str(url).startswith(("http://", "https://")):
        return "BŁĄD: URL musi zaczynać się od http:// lub https://"
    try:
        final_url, html = fetch_page(url)
    except HTTPError as e:
        logger.warning("read_webpage HTTPError for %s: %s", url, e)
        return f"BŁĄD: Strona zwróciła HTTP {e.code}."
    except URLError as e:
        if isinstance(e.reason, ssl.SSLError):
            logger.warning("read_webpage TLS error for %s: %s", url, e.reason)
            return "BŁĄD: Problem z TLS/SSL przy pobieraniu strony."
        logger.warning("read_webpage URLError for %s: %s", url, e)
        return f"BŁĄD: Nie udało się połączyć ze stroną. Szczegóły: {e.reason}"
    except Exception as e:
        logger.warning("read_webpage unexpected error for %s: %s", url, e)
        return f"BŁĄD: Nie udało się pobrać strony: {e}"

    title = _extract_title(html)
    text = _clean_html(html)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... skrócono ...]"

    return json.dumps(
        {"title": title, "url": final_url, "content": text},
        ensure_ascii=False,
    )
