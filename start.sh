#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PORT=7331

# Läuft der Server schon?
if lsof -ti:$PORT &>/dev/null; then
  echo "Server läuft bereits auf Port $PORT"
  xdg-open "http://localhost:$PORT" 2>/dev/null &
  exit 0
fi

# Server starten
echo "✂️  Starte Schnittmuster-DB..."
./venv/bin/python server.py &
SERVER_PID=$!

# Kurz warten bis Server bereit
sleep 1.5

# Browser öffnen
xdg-open "http://localhost:$PORT" 2>/dev/null &

echo "Server läuft (PID $SERVER_PID). Fenster schliessen beendet den Server."
wait $SERVER_PID
