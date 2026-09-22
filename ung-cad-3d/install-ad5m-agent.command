#!/bin/bash
set -e
DIR="$HOME/.ung-cad"
mkdir -p "$DIR"
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then echo "Python 3 is required"; exit 1; fi
"$PY" -m pip install --user --upgrade flashforge-python-api
curl -fsSL "https://ung-cad-3d-production.up.railway.app/ung-cad-ad5m-bridge.py" -o "$DIR/ung-cad-ad5m-bridge.py"
read -r -p "Enter the AD5M Access / Check Code once: " CODE
cat > "$DIR/agent.env" <<EOF
UNG_CAD_PRINTER_ID=a51a5435
UNG_CAD_CHECK_CODE=$CODE
UNG_CAD_CLOUD=https://ung-cad-3d-production.up.railway.app
EOF
chmod 600 "$DIR/agent.env"
PLIST="$HOME/Library/LaunchAgents/com.ung.cad.ad5m.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.ung.cad.ad5m</string>
<key>ProgramArguments</key><array><string>/bin/bash</string><string>-lc</string><string>set -a; source "$DIR/agent.env"; set +a; exec "$PY" "$DIR/ung-cad-ad5m-bridge.py"</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>$DIR/agent.log</string><key>StandardErrorPath</key><string>$DIR/agent-error.log</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/com.ung.cad.ad5m"
echo "UNG-CAD AD5M agent installed. It will start automatically at login and restart if it stops."
