"""
todo.py — zarządzanie plikiem TODO.md

Funkcje:
  1. Przeniesienie ukończonych zadań (- [x]) do sekcji ## Zrobione
  2. Usunięcie zadań z sekcji Zrobione starszych niż TODO_DONE_MAX_AGE_DAYS
  3. Grupowanie aktywnych zadań przez OpenAI:
       ## Do zrobienia od razu  (≤15 min)
       ## Krótkie               (do 1h)
       ## Wymagają czasu        (>1h lub złożone)
       ## Czeka na coś          (zależności, termin)
"""

import re
import os
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from openai import OpenAI

from config import TODO_FILE, TODO_DONE_MAX_AGE_DAYS, TODO_QUICK_MAX_MINUTES, OPENAI_MODEL, OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

# ── Typy danych ──────────────────────────────────────────────────────────────

class Task(NamedTuple):
    text: str
    done: bool
    done_date: str      # "YYYY-MM-DD" lub ""

class GroupedTasks(NamedTuple):
    quick:   list[str]
    short:   list[str]
    long:    list[str]
    waiting: list[str]

# ── Parsowanie ───────────────────────────────────────────────────────────────

TASK_RE      = re.compile(r'^- \[( |x)\] (.+)$', re.MULTILINE)
DONE_DATE_RE = re.compile(r'✓ (\d{4}-\d{2}-\d{2})$')

def parse_tasks(content: str) -> list[Task]:
    tasks = []
    for match in TASK_RE.finditer(content):
        done = match.group(1) == "x"
        text = match.group(2).strip()
        date_match = DONE_DATE_RE.search(text)
        done_date = date_match.group(1) if date_match else ""
        clean_text = DONE_DATE_RE.sub("", text).strip()
        tasks.append(Task(clean_text, done, done_date))
    return tasks


def split_sections(content: str) -> tuple[str, str, str]:
    done_header_match = re.search(r'^## Zrobione.*$', content, re.MULTILINE)
    if done_header_match:
        active_block = content[:done_header_match.start()]
        done_block   = content[done_header_match.start():]
    else:
        active_block = content
        done_block   = ""
    return active_block, done_block


def is_expired(done_date: str) -> bool:
    if not done_date:
        return False
    try:
        dt = datetime.strptime(done_date, "%Y-%m-%d").date()
        return (date.today() - dt).days > TODO_DONE_MAX_AGE_DAYS
    except ValueError:
        return False

# ── Grupowanie przez OpenAI ──────────────────────────────────────────────────

def group_tasks_with_ai(tasks: list[str]) -> GroupedTasks:
    if not tasks:
        return GroupedTasks([], [], [], [])

    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks))
    prompt = f"""Masz listę zadań do zrobienia. Podziel każde z nich na jedną z 4 grup:

- "quick"   — można zrobić od razu, zajmie max {TODO_QUICK_MAX_MINUTES} minut
- "short"   — zajmie do 1 godziny, niezbyt złożone
- "long"    — zajmie ponad godzinę lub wymaga myślenia/planowania/wielu kroków
- "waiting" — zależy od kogoś innego, ma konkretny termin w przyszłości, lub czeka na zewnętrzny warunek

Zadania:
{numbered}

Odpowiedz TYLKO jako JSON, zero innych słów:
{{
  "quick":   [numery zadań],
  "short":   [numery zadań],
  "long":    [numery zadań],
  "waiting": [numery zadań]
}}"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    data = json.loads(match.group() if match else raw)

    def pick(indices: list) -> list[str]:
        result = []
        for i in indices:
            idx = int(i) - 1
            if 0 <= idx < len(tasks):
                result.append(tasks[idx])
        return result

    return GroupedTasks(
        quick=pick(data.get("quick", [])),
        short=pick(data.get("short", [])),
        long=pick(data.get("long", [])),
        waiting=pick(data.get("waiting", [])),
    )

# ── Budowanie pliku ──────────────────────────────────────────────────────────

def build_todo_file(grouped: GroupedTasks, done_tasks: list[Task], header: str) -> str:
    lines = [header.rstrip(), ""]

    def section(title: str, tasks: list[str]):
        if not tasks:
            return
        lines.append(f"## {title}")
        lines.append("")
        for t in tasks:
            lines.append(f"- [ ] {t}")
        lines.append("")

    section("Do zrobienia od razu", grouped.quick)
    section("Krótkie", grouped.short)
    section("Wymagają czasu", grouped.long)
    section("Czeka na coś", grouped.waiting)

    fresh_done = [t for t in done_tasks if not is_expired(t.done_date)]
    if fresh_done:
        lines.append("## Zrobione")
        lines.append("")
        for t in fresh_done:
            date_str = f" ✓ {t.done_date}" if t.done_date else ""
            lines.append(f"- [x] {t.text}{date_str}")
        lines.append("")

        expired_count = len(done_tasks) - len(fresh_done)
        if expired_count:
            lines.append(f"*{expired_count} starszych wpisów automatycznie usuniętych*")
            lines.append("")

    return "\n".join(lines)


def extract_header(content: str) -> str:
    first_task = re.search(r'^- \[', content, re.MULTILINE)
    first_section = re.search(r'^## ', content, re.MULTILINE)

    cut = None
    if first_task and first_section:
        cut = min(first_task.start(), first_section.start())
    elif first_task:
        cut = first_task.start()
    elif first_section:
        cut = first_section.start()

    return content[:cut].rstrip() if cut else content.rstrip()

# ── Główna funkcja ───────────────────────────────────────────────────────────

def process_todo(dry_run: bool = True, todo_path: Path = TODO_FILE) -> None:
    if not todo_path.exists():
        print(f"❌ Nie znaleziono pliku TODO: {todo_path}")
        return

    content = todo_path.read_text(encoding="utf-8")
    header  = extract_header(content)
    tasks   = parse_tasks(content)

    active_tasks = [t for t in tasks if not t.done]
    done_tasks   = [t for t in tasks if t.done]

    today = date.today().isoformat()
    done_with_dates = [
        Task(t.text, t.done, t.done_date or today)
        for t in done_tasks
    ]

    expired = [t for t in done_with_dates if is_expired(t.done_date)]

    print(f"\n📋 TODO: {len(active_tasks)} aktywnych | {len(expired)} do usunięcia z sekcji Zrobione (>{TODO_DONE_MAX_AGE_DAYS} dni)")

    if not active_tasks:
        print("   Brak aktywnych zadań do grupowania.")
        grouped = GroupedTasks([], [], [], [])
    else:
        print("\n🤖 Grupuję zadania przez OpenAI...")
        grouped = group_tasks_with_ai([t.text for t in active_tasks])

        print(f"\n   Do zrobienia od razu : {len(grouped.quick)}")
        print(f"   Krótkie              : {len(grouped.short)}")
        print(f"   Wymagają czasu       : {len(grouped.long)}")
        print(f"   Czeka na coś         : {len(grouped.waiting)}")

    if dry_run:
        print("\n👁  DRY RUN — podgląd grupowania:\n")
        if grouped.quick:
            print("  ## Do zrobienia od razu")
            for t in grouped.quick:
                print(f"     - [ ] {t}")
        if grouped.short:
            print("  ## Krótkie")
            for t in grouped.short:
                print(f"     - [ ] {t}")
        if grouped.long:
            print("  ## Wymagają czasu")
            for t in grouped.long:
                print(f"     - [ ] {t}")
        if grouped.waiting:
            print("  ## Czeka na coś")
            for t in grouped.waiting:
                print(f"     - [ ] {t}")
        if expired:
            print(f"\n  🗑  Usunięto by {len(expired)} ukończonych (starsze niż {TODO_DONE_MAX_AGE_DAYS} dni)")
        print("\n  Uruchom z --apply żeby zapisać.")
        return

    new_content = build_todo_file(grouped, done_with_dates, header)
    todo_path.write_text(new_content, encoding="utf-8")
    print(f"\n✅ TODO zapisane: {todo_path}")


# ── Operacje atomowe ─────────────────────────────────────────────────────────

def add_task(text: str, todo_path: Path = TODO_FILE) -> bool:
    """Dopisuje nowe zadanie na końcu aktywnych (przed sekcją ## Zrobione)."""
    if not todo_path.exists():
        return False

    content = todo_path.read_text(encoding="utf-8")
    active_block, done_block = split_sections(content)

    new_line = f"\n- [ ] {text.strip()}"
    new_content = active_block.rstrip() + new_line + "\n"
    if done_block:
        new_content += "\n" + done_block

    todo_path.write_text(new_content, encoding="utf-8")
    return True


def complete_task_by_text(query: str, todo_path: Path = TODO_FILE) -> tuple[list[str], int]:
    """
    Oznacza zadanie pasujące do query jako ukończone ([x] + data).

    Returns:
        (matched_tasks, count_marked) — lista pasujących tekstów i ile faktycznie oznaczono.
        Jeśli matched_tasks ma > 1 element, oznaczenie NIE następuje (agent pyta użytkownika).
    """
    if not todo_path.exists():
        return [], 0

    content = todo_path.read_text(encoding="utf-8")
    tasks = parse_tasks(content)
    active = [t for t in tasks if not t.done]

    query_lower = query.lower()
    matches = [t for t in active if query_lower in t.text.lower()]

    if len(matches) != 1:
        return [t.text for t in matches], 0

    today = date.today().isoformat()
    target_text = matches[0].text

    def replace_task(m: re.Match) -> str:
        done_flag = m.group(1)
        text_body = m.group(2).strip()
        clean = DONE_DATE_RE.sub("", text_body).strip()
        if done_flag == " " and clean == target_text:
            return f"- [x] {clean} ✓ {today}"
        return m.group(0)

    new_content = TASK_RE.sub(replace_task, content)
    todo_path.write_text(new_content, encoding="utf-8")

    # Po oznaczeniu zadania jako ukończone od razu porządkujemy plik,
    # aby wpis trafił do sekcji "## Zrobione".
    process_todo(dry_run=False, todo_path=todo_path)
    return [target_text], 1


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--vault", help="Nadpisuje VAULT_PATH z config.py")
    args = parser.parse_args()

    if args.vault:
        path = Path(args.vault).expanduser() / "00_System" / "TODO.md"
    else:
        path = TODO_FILE

    process_todo(dry_run=not args.apply, todo_path=path)
