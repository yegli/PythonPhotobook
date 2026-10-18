#!/bin/bash
# macOS: double-click to start Photobook. The very first start installs what it needs (about a minute).
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "First start: setting up Photobook (one time only, needs internet)..."
  if ! { python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt; }; then
    rm -rf .venv
    echo "Setup failed. Please install Python from https://www.python.org/downloads/ and try again."
    read -r -p "Press Enter to close."
    exit 1
  fi
fi
.venv/bin/python photobook.py
