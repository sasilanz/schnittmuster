#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "✂️  Schnittmuster-DB — Installation"
echo ""

# Python prüfen
if ! command -v python3 &>/dev/null; then
  echo "FEHLER: python3 nicht gefunden. Bitte installieren: sudo apt install python3 python3-venv"
  exit 1
fi

# venv erstellen
if [ ! -d "venv" ]; then
  echo "→ Erstelle virtuelle Umgebung..."
  python3 -m venv venv
fi

# Dependencies installieren
echo "→ Installiere Abhängigkeiten..."
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet flask python-dotenv anthropic pillow

# Ordner anlegen
mkdir -p data/scans data/bilder backups

# .env prüfen
if [ ! -f ".env" ]; then
  echo ""
  echo "→ Bitte API-Key eintragen:"
  echo "  echo 'ANTHROPIC_API_KEY=sk-ant-...' > $DIR/.env"
fi

echo ""
echo "✓ Installation abgeschlossen!"
echo "  Starten: ./start.sh"
