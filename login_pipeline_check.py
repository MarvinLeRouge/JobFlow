#!/usr/bin/env python3
"""Login-triggered prompt to run the JobFlow pipeline, at most once per
calendar day.

Two-stage, both stages run this same script:
- Launched directly by the XDG autostart entry (no terminal attached): if
  today's check is already done, exits silently. Otherwise it re-launches
  itself inside a terminal via x-terminal-emulator, this time with
  --prompt.
- Launched with --prompt (always inside a terminal, by the step above):
  skips the date gate and asks the user directly whether to run the
  pipeline.

Usage: python3 login_pipeline_check.py [--prompt]
"""

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
LOGS_DIR = ROOT / "logs"
MARKER_FILE = LOGS_DIR / "last_pipeline_check.json"


def already_checked_today() -> bool:
    if not MARKER_FILE.exists():
        return False
    with MARKER_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    return data.get("last_check_date") == date.today().isoformat()


def mark_checked_today() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    MARKER_FILE.write_text(
        json.dumps({"last_check_date": date.today().isoformat()}), encoding="utf-8"
    )


def prompt_and_maybe_run() -> None:
    mark_checked_today()
    answer = input("Lancer le pipeline JobFlow ? [o/N] ").strip().lower()
    if answer in ("o", "oui", "y", "yes"):
        subprocess.run([str(ROOT / ".venv" / "bin" / "python"), str(ROOT / "run_pipeline.py")])
    input("Appuyez sur Entree pour fermer...")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prompt", action="store_true", help="internal: skip the date gate, ask directly"
    )
    args = parser.parse_args()

    if args.prompt:
        prompt_and_maybe_run()
        return

    if already_checked_today():
        return

    subprocess.Popen(
        ["x-terminal-emulator", "-e", sys.executable, str(Path(__file__).resolve()), "--prompt"]
    )


if __name__ == "__main__":
    main()
