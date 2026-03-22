"""
agent/skills/yt_transcript.py — skill pobierania transkrypcji z YouTube.

Eksportuje:
    SKILL              — instrukcje LLM + definicja narzędzia dla function calling
    YT_TRANSCRIPT_TOOLS — specyfikacja narzędzia w formacie OpenAI
    fetch_transcript   — implementacja wywoływana z execute_tool() w sub-agencie
"""

import re
import logging
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

logger = logging.getLogger(__name__)

DEFAULT_LANG_PRIORITY = ["pl", "en"]


def extract_video_id(url: str) -> str:
    """Wyciąga 11-znakowe video ID z URL lub zwraca ID jeśli już nim jest."""
    m = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})", url)
    if m:
        return m.group(1)
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url
    raise ValueError(f"Nie można wyciągnąć video ID z: {url}")


def _get_transcript_segments(
    video_id: str, lang_priority: list[str]
) -> tuple[list, str]:
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)

    for lang in lang_priority:
        try:
            t = transcript_list.find_transcript([lang])
            fetched = t.fetch()
            return list(fetched), fetched.language_code
        except NoTranscriptFound:
            continue

    # Fallback: pierwszy dostępny język
    for t in transcript_list:
        fetched = t.fetch()
        return list(fetched), fetched.language_code

    raise NoTranscriptFound(video_id, lang_priority)


def _get_metadata(video_id: str) -> dict:
    try:
        import yt_dlp

        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
            return {
                "title": info.get("title", ""),
                "author": info.get("uploader", ""),
                "duration_sec": info.get("duration", 0),
                "upload_date": info.get("upload_date", ""),
            }
    except ImportError:
        logger.warning("yt-dlp nie jest zainstalowane — metadane niedostępne")
        return {}
    except Exception as e:
        logger.warning(f"Nie udało się pobrać metadanych (video_id={video_id}): {e}")
        return {}


def fetch_transcript(
    url: str,
    lang: str = "pl,en",
    include_meta: bool = False,
) -> dict:
    """
    Główna funkcja do wywołania przez agenta via execute_tool().

    Returns:
        dict: {video_id, lang, transcript} + opcjonalnie metadane

    Raises:
        ValueError: gdy nie można wyciągnąć video ID
        TranscriptsDisabled: gdy transkrypcje są wyłączone dla tego filmu
        NoTranscriptFound: gdy żaden z żądanych języków nie jest dostępny
    """
    lang_priority = [l.strip() for l in lang.split(",") if l.strip()]
    video_id = extract_video_id(url)
    segments, used_lang = _get_transcript_segments(video_id, lang_priority)
    text = " ".join(s.text.strip() for s in segments)

    result: dict = {"video_id": video_id, "lang": used_lang, "transcript": text}

    if include_meta:
        result.update(_get_metadata(video_id))

    return result


YT_TRANSCRIPT_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_yt_transcript",
            "description": (
                "Pobiera transkrypcję filmu z YouTube. "
                "Zwraca tekst transkrypcji, video_id i kod języka. "
                "Opcjonalnie dołącza metadane (tytuł, autor, długość, data publikacji). "
                "Metadane wymagają zainstalowanego yt-dlp."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL filmu YouTube lub 11-znakowe video ID",
                    },
                    "lang": {
                        "type": "string",
                        "description": (
                            "Języki po przecinku, w kolejności priorytetów. "
                            "Domyślnie: 'pl,en'"
                        ),
                    },
                    "include_meta": {
                        "type": "boolean",
                        "description": (
                            "Czy dołączyć metadane (tytuł, autor, czas trwania). "
                            "Wymaga yt-dlp. Domyślnie false."
                        ),
                    },
                },
                "required": ["url"],
            },
        },
    }
]

SKILL: dict = {
    "name": "yt_transcript",
    "instructions": (
        "Potrafisz pobierać transkrypcje filmów z YouTube i zapisywać notatki do vaultu.\n\n"
        "Gdy użytkownik podaje link do YouTube lub prosi o analizę / streszczenie / notatkę z filmu:\n"
        "1. Wywołaj get_yt_transcript żeby pobrać transkrypcję (domyślnie lang='pl,en')\n"
        "2. Na podstawie transkrypcji napisz notatkę Markdown zawierającą:\n"
        "   - frontmatter z tagami i datą\n"
        "   - źródło (URL filmu)\n"
        "   - streszczenie w punktach\n"
        "   - kluczowe wnioski / cytaty\n"
        "3. Wybierz jedną kategorię treści z listy: {YT_CATEGORIES}. "
        "System sam wybierze właściwy podfolder w 03_Knowledge i odpowiedni link hubu.\n"
        "4. ZAWSZE wywołaj save_note żeby zapisać notatkę do vaultu - nie pytaj, po prostu zapisz.\n"
        "   Pole folder używaj tylko gdy użytkownik wyraźnie chce inną ścieżkę niż wynika z kategorii.\n"
        "   W polu content podaj treść bez YAML frontmatter (dodaje go system: category + wikilink hubu).\n"
        "5. Jeśli transkrypcje są wyłączone lub niedostępne - poinformuj użytkownika\n\n"
        "Jeśli użytkownik chce przenieść lub zmienić kategorię notatki już zapisanej w 03_Knowledge "
        "(np. zła kategoria przy zapisie): użyj read_knowledge_note (opcjonalnie) i relocate_yt_note "
        "ze ścieżką względem 03_Knowledge oraz nową kategorią; dla treści poza mapowaniem (np. fotografia) "
        "możesz użyć kategorii 'inne' i parametru folder z jednym segmentem (np. Photography).\n\n"
        "Nie wyświetlaj tylko tekstu - każda sesja z filmem kończy się zapisaną notatką."
    ),
    "tools": YT_TRANSCRIPT_TOOLS,
    "output_format": "Transkrypcja lub streszczenie w języku polskim. Cytaty z transkrypcji jako bloki kodu.",
}
