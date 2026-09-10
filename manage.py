#!/usr/bin/env python
"""CLI local do projeto PIBIC LAB baseado no Vela Framework."""
from __future__ import annotations

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from vela.cli.commands import CommandRunner  # noqa: E402


def main() -> None:
    runner = CommandRunner()
    runner.execute(sys.argv[1:])


if __name__ == "__main__":
    main()
