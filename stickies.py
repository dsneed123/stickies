#!/usr/bin/env python3
"""Launcher: run ./stickies.py, or install.sh to get a desktop entry."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stickies.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
