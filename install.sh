#!/usr/bin/env bash
# FRIDAY — one-shot installer (Ubuntu/GNOME friendly)
set -euo pipefail

DST="${1:-$HOME/.local/share/friday}"
SRC="$(cd "$(dirname "$0")" && pwd)"

echo "FRIDAY installer → $DST"

# 1. runtime python deps (openai, vosk for the off-line voice, pyttsx3 TTS)
pip3 install --user --break-system-packages -q openai vosk pyttsx3 2>/dev/null || \
python3 -m pip install --user -q openai vosk pyttsx3

# 2. Vosk acoustic model (off-line, ~41 MB) — only if missing
MODEL_DIR="${VOSK_MODEL:-$HOME/.local/share/friday/model}"
if [ ! -d "$MODEL_DIR" ]; then
  echo "downloading vosk small-en-us model…"
  TMP="$(mktemp -d)"
  curl -sL -o "$TMP/vm.zip" https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
  (cd "$TMP" && unzip -q vm.zip && mv vosk-model-small-en-us-0.15 "$MODEL_DIR")
  rm -rf "$TMP"
fi

# 3. copy app into place
mkdir -p "$DST"
rm -rf "$DST"/friday_web.py "$DST"/friday_ui.html \
       "$DST"/friday_voice.py "$DST"/friday_app.py "$DST"/friday.svg
cp "$SRC"/friday_web.py "$SRC"/friday_ui.html \
   "$SRC"/friday_voice.py "$SRC"/friday_app.py "$SRC"/friday.svg "$DST"/
chmod +x "$DST"/friday_app.py

# 4. desktop entry
mkdir -p "$HOME/.local/share/applications"
sed -e "s|__DST__|$DST|g" "$SRC"/friday.desktop > "$HOME/.local/share/applications/friday.desktop"
chmod +x "$HOME/.local/share/applications/friday.desktop"

echo "installed. Launch with:  python3 $DST/friday_app.py"
echo "or search 'FRIDAY' in your app grid."