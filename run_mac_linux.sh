#!/usr/bin/env bash
# First run sets everything up, later runs just start the app.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install --upgrade pip
  .venv/bin/pip install -r requirements.txt
  .venv/bin/python -m playwright install chromium
fi
exec .venv/bin/python main.py
