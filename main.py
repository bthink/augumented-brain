"""
main.py — punkt wejścia dla Augmented Brain.

Tryby działania:
    python main.py                  → interaktywny chat z orchestratorem
    python main.py --auto           → tryb automatyczny (cron): inbox + todo
    python main.py --dry-run        → symulacja bez zapisu
    python main.py --legacy         → stare menu (tasks/)
"""

import argparse
import logging
import sys


def run_interactive():
    """Interaktywny chat z orchestratorem."""
    from agent.orchestrator import Orchestrator

    print("🧠 Augmented Brain — tryb interaktywny")
    print("Wpisz komendę lub 'exit' aby wyjść.\n")

    orch = Orchestrator(dry_run=False)

    while True:
        try:
            user_input = input("▶ ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nDo widzenia!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            break

        result = orch.run(user_input)
        print(f"\n{result}\n")


def run_auto(dry_run: bool = False):
    """Tryb automatyczny dla cron — przetwarza inbox i todo."""
    from agent.orchestrator import Orchestrator

    logger.info("Tryb automatyczny — start")
    orch = Orchestrator(dry_run=dry_run)
    result = orch.run("ogarnij inbox i todo")
    print(result)
    logger.info("Tryb automatyczny — koniec")


def run_legacy():
    """Stare menu z tasks/ — kompatybilność wsteczna."""
    print("⚠️  Tryb legacy — stare menu zadań")
    # Import starego main jeśli istnieje
    try:
        import importlib
        legacy = importlib.import_module("tasks.__legacy_menu")
        legacy.run()
    except ImportError:
        print("Brak legacy menu. Użyj trybu interaktywnego.")


def main():
    parser = argparse.ArgumentParser(description="Augmented Brain — osobisty system AI")
    parser.add_argument("--auto", action="store_true", help="Tryb automatyczny (cron)")
    parser.add_argument("--dry-run", action="store_true", help="Symulacja bez zapisu")
    parser.add_argument("--legacy", action="store_true", help="Stare menu zadań")
    parser.add_argument("prompt", nargs="?", help="Jednorazowa komenda")
    args = parser.parse_args()

    if args.legacy:
        run_legacy()
    elif args.auto:
        run_auto(dry_run=args.dry_run)
    elif args.prompt:
        # Jednorazowa komenda: python main.py "ogarnij inbox"
        from agent.orchestrator import Orchestrator
        orch = Orchestrator(dry_run=args.dry_run)
        print(orch.run(args.prompt))
    else:
        run_interactive()


if __name__ == "__main__":
    main()