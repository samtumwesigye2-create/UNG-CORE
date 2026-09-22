#!/bin/bash
set -u
cd "$(dirname "$0")"
clear
echo "UNG-CAD AD5M Bridge"
echo "==================="
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
else
  echo "ERROR: Python 3 is required."
  read -r -p "Press Return to close..."
  exit 1
fi
echo "Preparing printer driver..."
"$PY" -m pip install --user --upgrade flashforge-python-api || {
  echo "ERROR: Could not install the FlashForge driver."
  read -r -p "Press Return to close..."
  exit 1
}
echo "Starting local bridge on 127.0.0.1:8765..."
"$PY" ung-cad-ad5m-bridge.py
rc=$?
echo "Bridge stopped (code $rc)."
read -r -p "Press Return to close..."
exit $rc
