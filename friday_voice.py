#!/usr/bin/env python3
"""
FRIDAY voice engine — offline wake word + speech-to-text.

Uses ALSA `arecord` to stream the mic (16 kHz, 16-bit mono) into Vosk.
Phases:
  * wake — grammar {friday, hey friday}: waits for the wake word
  * listen — free dictation: captures a command until short silence / timeout
Reports state to the FRIDAY server via /api/wake/state so the UI can react.

Stops automatically while the UI is recording (POST /api/wake/hold) to keep
the two mics from fighting.
"""

import io
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse

MODEL_DIR = os.environ.get(
    "VOSK_MODEL", os.path.expanduser("~/.local/share/friday/model"))
SERVER = os.environ.get("FRIDAY_VSERVER", "http://127.0.0.1:8300")

WAKE_WORDS = ["friday", "hey friday"]
MIN_BYTES = 640  # ~20ms
MAX_CMD_SECONDS = 8.0
SILENCE_SECONDS = 1.6
VOSK_DEF = {"wake": "off"}


def log(msg):
    print("[voice]", msg, flush=True)


class Voice:
    def __init__(self):
        import vosk
        self.vosk = vosk
        self.model = vosk.Model(MODEL_DIR)
        self.arecord = None
        self.buf = io.BytesIO()
        self.weak = threading.Event()
        self.wake = "off"
        # wake recognizer: grammar so any noise either == a wake phrase or [unk]
        self.wake_rec = vosk.KaldiRecognizer(self.model, 16000,
                                             '["%s", "[unk]"]' % '", "'.join(WAKE_WORDS))
        self.cmd_rec = vosk.KaldiRecognizer(self.model, 16000)

    # ---------- audio plumbing ----------
    def _open_mic(self):
        self._close_mic()
        self.arecord = subprocess.Popen(
            ["arecord", "-q", "-D", "default", "-f", "S16_LE",
             "-r", "16000", "-c", "1", "-t", "raw"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.buf = io.BytesIO()

    def _close_mic(self):
        if self.arecord:
            try:
                self.arecord.terminate()
            except Exception:
                pass
            self.arecord = None

    def _noop_drain(self):
        pass

    # ---------- state sync to server ----------
    def _state(self, **kw):
        if self.weak.is_set():
            return
        try:
            data = json.dumps({"wake": self.wake, **kw}).encode()
            req = urllib.request.Request(
                SERVER + "/api/wake/state", data=data,
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=1).read()
        except Exception:
            pass

    def _held(self):
        try:
            with urllib.request.urlopen(SERVER + "/api/wake/hold", timeout=0.6) as r:
                return json.loads(r.read())["held"]
        except Exception:
            return False

    def _say(self, text):
        try:
            data = json.dumps({"text": text}).encode()
            req = urllib.request.Request(SERVER + "/api/say", data=data,
                                         headers={"Content-Type": "application/json"},
                                         method="POST")
            urllib.request.urlopen(req, timeout=1).read()
        except Exception:
            pass

    # ---------- main loop ----------
    def run(self):
        if not shutil_have("arecord"):
            log("arecord missing — install alsa-utils")
            return
        self.wake = "listening"
        self._state()
        self._open_mic()
        log("wake word armed — say \"Hey FRIDAY\"")
        try:
            while not self.weak.is_set():
                if self._held():
                    time.sleep(0.4)
                    continue
                raw = self.arecord.stdout.read(4096)
                if not raw:
                    time.sleep(0.05)
                    continue
                if self.wake == "listening":
                    if self.wake_rec.AcceptWaveform(raw):
                        res = json.loads(self.wake_rec.Result())
                        if any(w in res.get("text", "") for w in WAKE_WORDS):
                            self._on_wake()
        except KeyboardInterrupt:
            pass
        finally:
            self._close_mic()
            self.wake = "off"
            self._state()
            log("voice stopped")

    def _on_wake(self):
        self.wake = "attentive"
        self._state()
        log("wake word heard")
        # No spoken "Yes?" — it gets picked up by the mic and breaks dictation.
        # The UI shows ATTENTIVE instantly as the acknowledgment.
        self._open_mic()  # fresher stream for dictation
        cmd = self._capture_command()
        self.wake = "listening"
        self._state()
        if cmd and not self.weak.is_set():
            log("command: " + cmd)
            try:
                data = json.dumps({"text": cmd, "via": "wake"}).encode()
                req = urllib.request.Request(
                    SERVER + "/api/ingest", data=data,
                    headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=2).read()
            except Exception as e:
                log("ingest failed: %s" % e)
        else:
            log("no command captured")

    def _capture_command(self):
        """Dictate up to MAX_CMD_SECONDS, stopping on a silence gap.
        Saves the raw audio to LAST_CAPTURE for forensics."""
        logs_dir = os.path.expanduser("~/.local/share/friday")
        os.makedirs(logs_dir, exist_ok=True)
        tee = open(os.path.join(logs_dir, "last_capture.raw"), "wb")
        self.cmd_rec = self.vosk.KaldiRecognizer(self.model, 16000)
        words = []
        last_speech = None
        end = time.time() + MAX_CMD_SECONDS
        while time.time() < end and not self.weak.is_set():
            if self._held():
                time.sleep(0.4)
                continue
            raw = self.arecord.stdout.read(4096)
            if not raw:
                time.sleep(0.05)
                continue
            tee.write(raw)
            if self.cmd_rec.AcceptWaveform(raw):
                res = json.loads(self.cmd_rec.Result())
                t = res.get("text", "").strip()
                if t:
                    words.append(t)
                    last_speech = time.time()
            else:
                if self.cmd_rec.PartialResult() and \
                   json.loads(self.cmd_rec.PartialResult()).get("partial", ""):
                    last_speech = time.time()
            if last_speech is not None and \
               time.time() - last_speech > SILENCE_SECONDS:
                break
        tee.close()
        text = " ".join(words)
        if not text:
            try:
                text = json.loads(self.cmd_rec.FinalResult()).get("text", "").strip()
            except Exception:
                pass
        log("capture: %r (len=%d)" % (text, os.path.getsize(
            os.path.join(logs_dir, "last_capture.raw"))))
        return text


def shutil_have(cmd):
    import shutil
    return shutil.which(cmd) is not None


def main():
    if not os.path.isdir(MODEL_DIR):
        print("FRIDAY voice: model missing at %s — run install.sh" % MODEL_DIR)
        sys.exit(1)
    v = Voice()
    try:
        v.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()