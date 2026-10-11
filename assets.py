"""Step 2 and 3: get a voiceover and a visual for each scene.

Voice:   edge-tts (free Microsoft neural voices, no API key needed).
Visuals: Pixabay or Pexels API (free keys) - stock video first, photo second.
Every step has an offline fallback so one failed API never kills the run.
"""
import asyncio
import os
import subprocess

import requests

VOICE = os.getenv("TTS_VOICE", "en-US-AndrewNeural")


def duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


# ---------- voiceover ----------

def make_voice(text: str, out_mp3: str) -> float:
    """Write narration audio to out_mp3 and return its length in seconds."""
    try:
        import edge_tts

        asyncio.run(edge_tts.Communicate(text, VOICE, rate="+5%").save(out_mp3))
    except Exception as e:  # no package, no network, etc.
        print(f"  TTS failed ({type(e).__name__}) -> silent placeholder")
        seconds = max(3.0, len(text.split()) / 2.6)  # ~156 wpm speaking pace
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{seconds:.2f}", out_mp3],
            check=True,
        )
    return duration(out_mp3)


# ---------- visuals ----------

def get_visual(query: str, out_base: str, min_seconds: float) -> str:
    """Return a path to a video (.mp4) or image (.jpg/.png) for this scene."""
    providers = [("Pixabay", "PIXABAY_API_KEY", _pixabay), ("Pexels", "PEXELS_API_KEY", _pexels)]
    for name, env, fetch in providers:
        key = os.getenv(env)
        if not key:
            continue
        try:
            return fetch(query, out_base, min_seconds, key)
        except Exception as e:
            print(f"  {name} failed for '{query}' ({e})")
    print("  no stock footage -> gradient placeholder")
    return _placeholder(out_base + ".png")


def _pixabay(query, out_base, min_seconds, key):
    params = {"key": key, "q": query[:100], "safesearch": "true", "per_page": 10}
    r = requests.get("https://pixabay.com/api/videos/", params=params, timeout=30)
    r.raise_for_status()
    # Prefer clips long enough to cover the narration (False sorts first).
    hits = sorted(r.json().get("hits", []), key=lambda h: h["duration"] < min_seconds)
    for h in hits:
        # "large" is often 4K or missing; "medium" is usually 1920x1080.
        for size in ("medium", "large", "small"):
            v = h["videos"].get(size) or {}
            if v.get("url") and v.get("width", 0) >= 1280:
                return _download(v["url"], out_base + ".mp4")

    r = requests.get("https://pixabay.com/api/", timeout=30,
                     params={**params, "image_type": "photo", "orientation": "horizontal"})
    r.raise_for_status()
    photos = r.json().get("hits", [])
    if photos:
        return _download(photos[0]["largeImageURL"], out_base + ".jpg")
    raise LookupError("no results")


def _pexels(query, out_base, min_seconds, key):
    h = {"Authorization": key}
    r = requests.get("https://api.pexels.com/videos/search", headers=h, timeout=30,
                     params={"query": query, "orientation": "landscape", "per_page": 10})
    r.raise_for_status()
    # Prefer clips long enough to cover the narration (False sorts first), then an HD file.
    videos = sorted(r.json().get("videos", []), key=lambda v: v["duration"] < min_seconds)
    for v in videos:
        files = [f for f in v["video_files"] if f.get("width") and 1280 <= f["width"] <= 1920]
        if files:
            return _download(max(files, key=lambda f: f["width"])["link"], out_base + ".mp4")

    r = requests.get("https://api.pexels.com/v1/search", headers=h, timeout=30,
                     params={"query": query, "orientation": "landscape", "per_page": 1})
    r.raise_for_status()
    photos = r.json().get("photos", [])
    if photos:
        return _download(photos[0]["src"]["large2x"], out_base + ".jpg")
    raise LookupError("no results")


def _download(url, path):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return path


def _placeholder(path):
    """Plain gradient frame used when no stock provider returns a visual.
    No text is drawn, so it works on any ffmpeg build (including ones without
    the drawtext filter)."""
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "gradients=s=1920x1080:c0=0x1d2b53:c1=0x7e2553:duration=1",
         "-frames:v", "1", path],
        check=True,
    )
    return path
