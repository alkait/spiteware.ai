#!/usr/bin/env python3
"""Narration for the daily short, through OpenRouter's speech endpoint.

Usage: python3 scripts/voice.py "text to say" out.wav

As a module, say(text) returns raw PCM (16-bit mono, RATE Hz). Takes are cached
in shorts/.cache by a hash of model, voice and text, so a re-render never pays
for the same line twice; scripts/short.py --reroll asks for a new take.

The key is OPENROUTER_API_KEY, from the environment or the repo's .env.
Stdlib only, like everything else here.
"""
import hashlib, json, os, pathlib, sys, urllib.error, urllib.request, wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "shorts" / ".cache"
MODEL = "google/gemini-3.1-flash-tts-preview"
VOICE = "Aoede"
RATE = 24000  # Gemini TTS only returns pcm: 16-bit mono at 24 kHz


def key():
    k = os.environ.get("OPENROUTER_API_KEY")
    env = ROOT / ".env"
    if not k and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                k = line.split("=", 1)[1].strip()
    if not k:
        sys.exit("No OPENROUTER_API_KEY in the environment or .env")
    return k


def say(text, model=MODEL, voice=VOICE, fresh=False):
    """PCM for text. Delivery cues go inline in the text, in [square brackets].
    fresh=True skips the cache: every take is a new performance, so this is the re-roll."""
    CACHE.mkdir(parents=True, exist_ok=True)
    hit = CACHE / (hashlib.sha1(f"{model}|{voice}|{text}".encode()).hexdigest()[:16] + ".pcm")
    if hit.exists() and not fresh:
        return hit.read_bytes()
    body = {"model": model, "voice": voice, "input": text, "response_format": "pcm"}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/audio/speech", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            pcm = resp.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"TTS failed, HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")
    if pcm[:1] == b"{" or len(pcm) < RATE:  # an error body, or under half a second of audio
        sys.exit(f"TTS returned no audio: {pcm[:300]!r}")
    hit.write_bytes(pcm)
    return pcm


def write_wav(path, pcm, rate=RATE):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    write_wav(sys.argv[2], say(sys.argv[1]))
    print(sys.argv[2])
