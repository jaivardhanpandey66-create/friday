# FRIDAY

Age-of-Ultron style command center for your Ubuntu PC. Wake word ("Hey FRIDAY"),
off-line speech recognition, and direct control of your machine — volume,
brightness, media keys, windows, typing, notifications, launching apps — with a
JARVIS holographic interface.

## What it is

- `friday_web.py` — stdlib HTTP server + agent (any OpenRouter model). Reuses
  your `~/.config/chip/key` like CHIP. Port **8300**.
- `friday_ui.html` — the holographic Age-of-Ultron interface (deep-indigo
  palette sampled from the reference GIF): rotating hexagonal emblem, arc
  diagnostics gauge, channel meters, scanlines, boot sequence.
- `friday_voice.py` — off-line wake word ("friday" / "hey friday") + free
  dictation via Vosk and `arecord` (no cloud audio).
- `friday_app.py` — WebKitGTK desktop window (no Electron) hosting the server
  and the voice engine in the background.

## Controls

Everything is a normal sentence:

- "open firefox" / "open the terminal"
- "volume up" / "set volume to 40" / "mute"
- "brightness down" / "set brightness 70"
- "next track" / "pause"
- "open spotify" / "type hello world" / "press super, then open files"
- "what's the system status?"
- "send a notification that dinner is ready"
- "remember my wifi password is ..." → shared CORTEX long-term memory
- "what do you remember about ..." → recalls from CORTEX

Security: `run` shell tool only executes with explicit user intent and blocks
destructive patterns. PLAN/read-only guard: `windows`, `system_info`, `recall`,
`screenshot` are always safe.

## Install

```bash
sudo apt install python3-gi gir1.2-webkit2-4.1 alsa-utils   # GTK + mic
./install.sh
python3 ~/.local/share/friday/friday_app.py                 # run
```

`install.sh` installs `openai`, `vosk`, `pyttsx3`, downloads the ~41 MB Vosk
en-us model, copies files to `~/.local/share/friday`, and adds a desktop entry.

Voice engine needs a working input device; wake spotter answers "Yes?" through
TTS (pyttsx3/espeak, female-ish voice) then captures your command.

## Sibling projects

| Project | Role |
| --- | --- |
| [chip](https://github.com/jaivardhanpandey66-create/chip) | holographic web agent |
| [jarvis](https://github.com/jaivardhanpandey66-create/jarvis) | home assistant playbook |
| [john](https://github.com/jaivardhanpandey66-create/john) | CLI sidekick |
| [stark](https://github.com/jaivardhanpandey66-create/stark) | real-time system telemetry |
| [cortex](https://github.com/jaivardhanpandey66-create/cortex) | shared long-term memory |

FRIDAY reads memory from CORTEX (port 8200) and telemetry from STARK (port 8100)
when they are running; it degrades gracefully without them.