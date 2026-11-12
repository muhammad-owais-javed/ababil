#!/bin/bash
set -eu

: "${VNC_PASSWORD:?VNC_PASSWORD must be set in .env}"
: "${SANDBOX_TOKEN:?SANDBOX_TOKEN must be set in .env}"
SIZE="${SCREEN_SIZE:-1280x800}"

# Remove stale X11 lock files from unclean shutdowns to prevent restart loops
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

Xvfb :1 -screen 0 "${SIZE}x24" -nolisten tcp &

# Wait until the screen accepts connections, instead of guessing with a fixed sleep.
for _ in $(seq 1 40); do
    [ -S /tmp/.X11-unix/X1 ] && break
    sleep 0.25
done
[ -S /tmp/.X11-unix/X1 ] || { echo "virtual screen did not start"; exit 1; }

fluxbox >/dev/null 2>&1 &
x11vnc -display :1 -forever -shared -passwd "$VNC_PASSWORD" -rfbport 5900 -quiet &
websockify --web /usr/share/novnc 6080 localhost:5900 &
python3 /opt/sandbox/api.py &

# If any part stops, exit.
wait -n
exit 1