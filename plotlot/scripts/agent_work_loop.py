#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# ///
# How to run
# python3 scripts/agent_work_loop.py --profile smoke
# python3 scripts/agent_work_loop.py --profile full
# python3 scripts/agent_work_loop.py --profile deploy-readiness --continue-on-failure

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from plotlot.dev.agent_loop_runner import main as run_agent_loop

    return run_agent_loop()


if __name__ == "__main__":
    raise SystemExit(main())
