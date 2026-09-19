#!/bin/bash
set -e
cd "$(dirname "$0")"
echo "Starting UNG-CAD AD5M Bridge..."
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3 is required on this Mac."
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi

"$PY" -m pip install --user --upgrade flashforge-python-api
"$PY" ung-cad-ad5m-bridge.py
