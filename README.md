# Topic → MP4 video generator (prototype)

Give it a topic, get back a narrated 1080p video with stock footage, burned-in captions and optional background music.

```bash
pip install -r requirements.txt     # also needs ffmpeg on PATH
cp .env.example .env                # add OpenRouter + Pixabay keys
python main.py "why octopuses are so smart" --music music.mp3
```

Output lands in `output/<topic>-<timestamp>/`, along with `script.json`, `captions.srt` and per-scene clips so any step can be inspected.

## How it works

| Step | File | What it does |
|---|---|---|
| 1. Script | `script.py` | An LLM via OpenRouter (NVIDIA Nemotron Ultra 3 free by default) writes 5–7 scenes as JSON, each with narration and a stock-footage search query. The output is validated before use. Claude via the Anthropic API is also supported. |
| 2. Voice | `assets.py` | edge-tts generates a voiceover per scene. Its real duration drives the timing for everything else. |
| 3. Visuals | `assets.py` | Pixabay API (Pexels also supported): stock video first, preferring clips long enough for the narration, photo second. |
| 4. Render | `render.py` | ffmpeg renders each scene to the same format, video loops/trims to the voice, photos get a Ken Burns zoom. Scenes are concatenated, then captions (SRT) are burned in and music is mixed under the voice. |

Every external call has a fallback (template script, silent audio, gradient placeholder), so one failing API degrades the video instead of crashing the run.

## What I'd add next

- **Word-accurate captions**: use edge-tts word boundaries (or Whisper) instead of proportional timing.
- **Smarter footage**: have the LLM pick between several stock results using thumbnails/descriptions; avoid reusing the same clip.
- **Vertical/Shorts mode**: 1080x1920 output flag.
- **Parallel scenes**: TTS + downloads + renders per scene run concurrently.
- **Job queue + UI**: wrap it as an API job in the Next.js app with status, retries and R2 upload.
- **Music library**: pick a royalty-free track by mood from the script.

Stock footage from [Pixabay](https://pixabay.com).
