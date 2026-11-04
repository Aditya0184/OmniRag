#!/bin/zsh
set -e
cd "${0:A:h}"
./.venv/bin/python scripts/mac_app.py start
open http://127.0.0.1:8000
