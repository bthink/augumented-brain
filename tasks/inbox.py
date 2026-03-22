"""
inbox.py — klasyfikacja notatek z folderu Inbox

Logika:
  1. Puste notatki z tytułem "Bez nazwy*" → usuń
  2. Pozostałe → klasyfikacja przez OpenAI:
       - todo   → dopisz na początku listy w 00_System/TODO.md
       - idea   → utwórz notatkę w 04_Ideas/
       - area   → utwórz notatkę w 02_Areas/<obszar>/
       - media  → dopisz do "Do obejrzenia i przeczytania.md"
       - delete → usuń
  3. Jeśli LLM niepewny lub typ=media → drugie wywołanie sprawdza
     czy to tytuł filmu/książki/gry (z krótkim opisem)
"""

import os
import re
import json
import shutil
from pathlib import Path
from dataclasses import dataclass

from openai import OpenAI

from config import (
    VAULT_PATH, FOLDERS, TODO_FILE, MEDIA_FILE,
    OPENAI_MODEL, OPENAI_API_KEY, AREAS
)

client = OpenAI(api_key=OPENAI_API_KEY)

# ── Typy ────────────────────────────────────────────────────────────────────

@dataclass
class ClassifiedNote:
    path: Path
    title: str
    content: str
    action: str          # delete | todo | idea | area | media
    area: str
    todo_text: str
    media_type: str
    media_title: str     # rzeczywisty tytuł medium (może różnić się od nazwy pliku)
    media_desc: str
    idea_title: str
    confidence: str      # high | low

# ── Helpers ──────────────────────────────────────────────────────────────────

def is_empty(content: str) -> bool:
    return not content.strip()

def is_unnamed(title: str) -> bool:
    return re.match(r'^Bez nazwy', title, re.IGNORECASE) is not None

def parse_json_response(raw: str) -> dict:
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(raw)


def slug_to_title(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("-", " ")).strip().lower()


def strip_leading_duplicate_title(content: str, *candidate_titles: str) -> str:
    if not content.strip():
        return ""

    normalized_candidates = {slug_to_title(t) for t in candidate_titles if t and t.strip()}
    if not normalized_candidates:
        return content.strip()

    lines = content.splitlines()
    first_non_empty_idx = None
    for idx, line in enumerate(lines):
        if line.strip():
            first_non_empty_idx = idx
            break

    if first_non_empty_idx is None:
        return ""

    first_line = lines[first_non_empty_idx].strip()
    heading_match = re.match(r"^#{1,6}\s+(.*)$", first_line)
    first_line_core = heading_match.group(1).strip() if heading_match else first_line

    if slug_to_title(first_line_core) in normalized_candidates:
        del lines[first_non_empty_idx]
        while lines and not lines[0].strip():
            lines.pop(0)
        return "\n".join(lines).strip()

    return content.strip()


def prepend_active_todo_item(todo_path: Path, task_text: str) -> None:
    line = f"- [ ] {task_text.strip()}\n"
    todo_path.parent.mkdir(parents=True, exist_ok=True)
    if not todo_path.exists():
        todo_path.write_text(line, encoding="utf-8")
        return

    content = todo_path.read_text(encoding="utf-8")
    done_match = re.search(r"^## Zrobione.*$", content, re.MULTILINE)
    if done_match:
        prefix = content[: done_match.start()]
        suffix = content[done_match.start() :]
    else:
        prefix = content
        suffix = ""

    first_task = re.search(r"^- \[ \] ", prefix, re.MULTILINE)
    if first_task:
        insert_at = first_task.start()
        new_content = prefix[:insert_at] + line + prefix[insert_at:] + suffix
    else:
        if prefix and not prefix.endswith("\n"):
            prefix = prefix + "\n"
        new_content = prefix + line + suffix

    todo_path.write_text(new_content, encoding="utf-8")


# ── Klasyfikacja ─────────────────────────────────────────────────────────────

def classify_note(title: str, content: str) -> dict:
    areas_list = ", ".join(AREAS)
    prompt = f"""Jesteś asystentem organizującym notatki w systemie PARA.
Przeanalizuj notatkę i zdecyduj co z nią zrobić.

Dostępne obszary (areas): {areas_list}

Możliwe akcje:
- "delete"  — notatka bez wartości, losowe znaki (TYLKO gdy treść jest bezsensowna, ignoruj tytuł)
- "todo"    — zadanie do zrobienia (zaczyna się od "Todo"/"todo" lub jest wyraźnym zadaniem)
- "idea"    — luźny pomysł, pytanie, obserwacja, coś do przemyślenia
- "area"    — dotyczy konkretnego obszaru życia/pracy z listy obszarów
- "media"   — może być tytuł filmu, książki, gry, serialu lub linku do obejrzenia/przeczytania

WAŻNE: Jeśli notatka ma jakąkolwiek sensowną treść — nigdy nie używaj "delete".
Oceniaj TREŚĆ, nie tytuł. Tytuł "Bez nazwy" jest bez znaczenia.

Tytuł notatki: "{title}"
Treść: "{content}"

Odpowiedz TYLKO jako JSON:
{{
  "action": "delete|todo|idea|area|media",
  "area": "nazwa obszaru lub ''",
  "todo_text": "tekst zadania bez prefixu Todo lub ''",
  "idea_title": "krótki tytuł dla pliku w ideas (max 5 słów) lub ''",
  "confidence": "high|low"
}}"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0,
    )
    return parse_json_response(response.choices[0].message.content.strip())


def lookup_media(title: str, content: str) -> dict:
    prompt = f"""Przeanalizuj notatkę i sprawdź czy zawiera tytuł filmu, książki, serialu lub gry.

Notatka (tytuł pliku): "{title}"
Treść: "{content}"

Treść może zaczynać się od prefiksu typu "film ", "książka ", "gra ", "serial " —
jeśli tak, prefiks wskazuje typ, a reszta to tytuł medium.
Np. treść "film hoppers" → media_type=film, media_title=Hoppers.

Jeśli to film lub serial — podaj gatunek i ocenę IMDB jeśli ją znasz (format: "Gatunek | ⭐ X.X/10 IMDB").
Jeśli to książka lub gra — podaj tylko gatunek, bez oceny IMDB.
Jeśli nie rozpoznajesz — zwróć is_media: false.

Odpowiedz TYLKO jako JSON:
{{
  "is_media": true,
  "media_type": "film|książka|serial|gra|inne",
  "media_title": "rozpoznany tytuł medium, np. 'Hoppers (2026)'",
  "description": "gatunek i ocena, np. 'Animacja, Sci-Fi | ⭐ 7.7/10 IMDB' lub ''"
}}"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=150,
        temperature=0,
    )
    return parse_json_response(response.choices[0].message.content.strip())


def classify_all(notes: list[Path]) -> list[ClassifiedNote]:
    results = []
    for path in notes:
        title = path.stem
        content = path.read_text(encoding="utf-8", errors="ignore").strip()

        if is_empty(content) and is_unnamed(title):
            results.append(ClassifiedNote(
                path=path, title=title, content=content,
                action="delete", area="", todo_text="",
                media_type="", media_title="", media_desc="", idea_title="",
                confidence="high"
            ))
            continue

        if is_empty(content) and not is_unnamed(title):
            results.append(ClassifiedNote(
                path=path, title=title, content=title,
                action="idea", area="", todo_text="",
                media_type="", media_title="", media_desc="", idea_title=title,
                confidence="high"
            ))
            continue

        data = classify_note(title, content)
        action = data.get("action", "idea")

        media_type = ""
        media_desc = ""

        media_title = ""

        if action == "media" or data.get("confidence") == "low":
            media_data = lookup_media(title, content)
            if media_data.get("is_media"):
                action = "media"
                media_type = media_data.get("media_type", "inne")
                media_title = media_data.get("media_title", "") or title
                media_desc = media_data.get("description", "")
            elif action == "media":
                action = "idea"

        if action == "delete" and not is_empty(content):
            action = "idea"

        results.append(ClassifiedNote(
            path=path,
            title=title,
            content=content,
            action=action,
            area=data.get("area", ""),
            todo_text=data.get("todo_text", "") or content,
            media_type=media_type,
            media_title=media_title,
            media_desc=media_desc,
            idea_title=data.get("idea_title", "") or title,
            confidence=data.get("confidence", "high"),
        ))

    return results

# ── Wykonanie akcji ───────────────────────────────────────────────────────────

def apply_delete(note: ClassifiedNote):
    note.path.unlink()
    print(f"     🗑  Usunięto: {note.title}")


def apply_todo(note: ClassifiedNote):
    text = note.todo_text.strip()
    prepend_active_todo_item(TODO_FILE, text)
    note.path.unlink()
    print(f"     ✅ TODO: {text}")


def apply_idea(note: ClassifiedNote):
    safe = re.sub(r'[^\w\s\-]', '', note.idea_title).strip().replace(' ', '-')
    target = VAULT_PATH / FOLDERS["ideas"] / f"{safe}.md"
    if target.exists():
        target = VAULT_PATH / FOLDERS["ideas"] / f"{safe}-{note.path.stem}.md"
    body = strip_leading_duplicate_title(note.content, note.idea_title, note.title, note.path.stem)
    content = f"[[Pomysły]]\n\n{body}\n" if body else "[[Pomysły]]\n"
    target.write_text(content, encoding="utf-8")
    note.path.unlink()
    print(f"     💡 Idea: {target.name}")


def apply_area(note: ClassifiedNote):
    area = note.area
    area_folder = VAULT_PATH / FOLDERS["areas"] / area
    area_folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[^\w\s\-]', '', note.title).strip().replace(' ', '-')
    target = area_folder / f"{safe}.md"
    body = strip_leading_duplicate_title(note.content, note.title, note.path.stem)
    content = f"[[{area}]]\n\n{body}\n" if body else f"[[{area}]]\n"
    target.write_text(content, encoding="utf-8")
    note.path.unlink()
    print(f"     📁 Area [{area}]: {target.name}")


def apply_media(note: ClassifiedNote):
    media_file = MEDIA_FILE
    if not media_file.exists():
        print(f"     ⚠️  Nie znaleziono pliku: {media_file}")
        return

    content = media_file.read_text(encoding="utf-8")
    mtype = note.media_type.lower()

    section_map = {
        "film":    "**Filmy**",
        "serial":  "**Filmy**",
        "książka": "**Książki**",
        "gra":     "**Gry**",
    }
    section = section_map.get(mtype, "**Inne**")

    display_title = note.media_title or note.title
    desc = f" — {note.media_desc}" if note.media_desc else ""
    new_entry = f"- {display_title}{desc}"

    if section in content:
        content = content.replace(section, f"{section}\n{new_entry}", 1)
    else:
        content += f"\n{section}\n{new_entry}\n"

    media_file.write_text(content, encoding="utf-8")
    note.path.unlink()
    print(f"     🎬 Media [{note.media_type}]: {display_title}{desc}")


# ── Główna funkcja ────────────────────────────────────────────────────────────

ACTION_LABELS = {
    "delete": "🗑  Usuń",
    "todo":   "✅ TODO",
    "idea":   "💡 Idea",
    "area":   "📁 Area",
    "media":  "🎬 Media",
}

def classify_and_preview(inbox_path: Path) -> list:
    notes = list(inbox_path.glob("*.md"))
    if not notes:
        print("✅ Inbox jest pusty.")
        return []

    print(f"\n📥 Inbox: {len(notes)} notatek")
    print("─" * 60)
    print("🤖 Klasyfikuję przez OpenAI...\n")

    classified = classify_all(notes)

    for note in classified:
        label = ACTION_LABELS.get(note.action, note.action)
        extra = ""
        if note.action == "area":
            extra = f" [{note.area}]"
        elif note.action == "media":
            extra = f" [{note.media_type}]"
            if note.media_desc:
                extra += f" — {note.media_desc}"
        elif note.action == "todo":
            extra = f": {note.todo_text[:50]}"
        conf = " ⚠️  " if note.confidence == "low" else ""
        print(f"  {conf}{label}{extra}")
        print(f"     \"{note.title}\" — {note.content[:60]}{'...' if len(note.content)>60 else ''}")

    counts = {}
    for n in classified:
        counts[n.action] = counts.get(n.action, 0) + 1

    print("\n" + "─" * 60)
    print("  " + " | ".join(f"{ACTION_LABELS[k]}: {v}" for k, v in counts.items()))
    return classified


def apply_classified(classified: list) -> None:
    print("\n💾 Zapisuję...\n")
    for note in classified:
        if note.action == "delete":
            apply_delete(note)
        elif note.action == "todo":
            apply_todo(note)
        elif note.action == "idea":
            apply_idea(note)
        elif note.action == "area":
            apply_area(note)
        elif note.action == "media":
            apply_media(note)
    print(f"\n✅ Przetworzono {len(classified)} notatek.")


def process_inbox(dry_run: bool = True):
    inbox_path = VAULT_PATH / FOLDERS["inbox"]
    if not inbox_path.exists():
        print(f"❌ Nie znaleziono folderu Inbox: {inbox_path}")
        return
    classified = classify_and_preview(inbox_path)
    if not classified:
        return
    if not dry_run:
        apply_classified(classified)
    else:
        print("\n  Uruchom z --apply żeby zapisać.")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    process_inbox(dry_run=not args.apply)
