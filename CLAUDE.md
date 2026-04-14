# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Augmented Brain is a terminal-based AI agent system that automatically manages an Obsidian vault organized with the PARA methodology (Projects, Areas, Resources, Archive). It processes inbox notes, manages a TODO list, transcribes YouTube videos, and performs web research - writing everything back to markdown files in the vault.

Vault path comes from `.env` (`VAULT_PATH`). The system uses OpenAI API (`gpt-4o-mini` by default).

## Running the System

```bash
python3 main.py                    # Interactive mode - chat loop with orchestrator
python3 main.py "ogarnij inbox"    # One-off command
python3 main.py --auto             # Cron mode: runs inbox + todo silently
python3 main.py --dry-run "..."    # Simulate without writing to vault
```

There is no formal test suite. Validate behavior with `--dry-run` against live vault data.

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Set VAULT_PATH and OPENAI_API_KEY
python3 main.py --dry-run "ogarnij inbox"
```

## Architecture

### Layer Stack (bottom → top)

```
Obsidian Vault (.md files)
    ↑
tasks/          Pure functions - no LLM, direct file/API operations
    ↑
agent/skills/   Composable instruction blocks injected into agent prompts
    ↑
sub_agents/     Domain agents with tool sets, run a ReAct loop
    ↑
agent/orchestrator.py   Routes natural-language commands to the right sub-agent
    ↑
main.py         Entry point, 3 modes
```

### ReAct Loop (`agent/base_agent.py`)

All sub-agents extend `BaseAgent`. Each iteration: LLM reasons → calls a tool → observes result → repeats until done. Max iterations is set per sub-agent. **Never modify `base_agent.py` for domain logic** - extend through skills and tools.

### Orchestrator (`agent/orchestrator.py`)

Parses the user command with LLM to decide which sub-agent to invoke. After the agent finishes, it runs an inbox verification step for certain commands.

### Sub-Agents

| Agent | File | Responsibility |
|---|---|---|
| InboxAgent | `sub_agents/inbox_agent.py` | Classify and move notes from `97_Inbox/` |
| TodoAgent | `sub_agents/todo_agent.py` | Read/write `00_System/TODO.md` |
| YoutubeAgent | `sub_agents/youtube_agent.py` | Fetch transcripts → save knowledge notes |
| ResearchAgent | `sub_agents/research_agent.py` | Web search + vault search → save research notes |
| OrphansAgent | `sub_agents/orphans_agent.py` | Find unlinked/stray notes |

### Skills (`agent/skills/`)

Skills are text blocks with optional tool definitions that get interpolated into agent system prompts. Registered in `agent/skills/__init__.py`. Available skills: `clarifier`, `para_classifier`, `time_estimator`, `yt_transcript`, `web_analyst`.

Skills can contain `{AREAS}` and similar placeholders - the loader fills them at runtime from `config.py`.

### Configuration (`config.py`)

Single source of truth for all constants:
- `VAULT_PATH`, `OPENAI_API_KEY` - from `.env`
- `FOLDERS` - PARA folder name mapping
- `AREAS` - dynamically loaded from `02_Areas/` subfolders at startup (new areas auto-discovered)
- `YT_KNOWLEDGE_BY_CATEGORY` - maps YouTube category → (folder, hub note name)
- `TODO_FILE`, `MEDIA_FILE` - paths to key vault files
- `OPENAI_MODEL` - currently `gpt-4o-mini`

### Task Modules (`tasks/`)

Pure functions called by sub-agents. No LLM calls inside tasks - those belong in agents/skills.

- `tasks/moc.py` - `update_hub_note()`: adds wikilinks to hub notes after saving new notes
- `tasks/inbox.py` - legacy classification logic
- `tasks/todo.py` - parse, group, and rewrite `TODO.md`
- `tasks/web_utils.py` - DuckDuckGo search, HTTP fetch
- `tasks/orphans.py` - find unlinked notes and vault root strays

### PARA Vault Structure

```
00_System/     TODO.md and system files
01_Projects/   Active projects
02_Areas/      Ongoing responsibilities (subfolders = areas, loaded as AREAS in config)
03_Knowledge/  Research/ and YouTube category subfolders
04_Ideas/      Media watchlist and ideas
97_Inbox/      Drop zone for unprocessed notes
98_Templates/
99_Archive/
```

## Extending the System

**Adding a new skill:** Create `agent/skills/my_skill.py`, register in `agent/skills/__init__.py`, then reference in target agent's `__init__`.

**Adding a new sub-agent:** Extend `BaseAgent`, implement `_get_tools()` and `_execute_tool()`, register in `orchestrator.py`'s routing logic.

**Adding a YouTube category:** Add entry to `YT_KNOWLEDGE_BY_CATEGORY` in `config.py` and add the category string to `YT_CATEGORIES`.

## Key Design Decisions

- **No LangGraph/LangChain** - ReAct loop is implemented in pure Python for full control (`agent/base_agent.py`)
- **`dry_run=True` is the safe default** - all write operations must be explicitly enabled
- **Obsidian CLI for file moves** - preserves wikilinks; falls back to `os.rename()` if CLI unavailable
- **Skills are composable** - agents declare which skills they need, not the other way around
- **AREAS is dynamic** - new `02_Areas/` subfolders are recognized without code changes

## Important Files

- `docs/architecture.md` - authoritative design document (442 lines), read before making architectural changes
- `.cursor/rules/agent-extension.mdc` - rules for extending agents safely
- `.cursor/rules/cursorrules.mdc` - project coding conventions
