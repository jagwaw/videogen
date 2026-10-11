"""Topic in, raw mp4 out.

    python main.py "why octopuses are so smart"
    python main.py "history of coffee" --music music.mp3

Pipeline: LLM script -> TTS voiceover per scene -> stock footage per scene
-> ffmpeg render per scene -> concat + burned-in captions (+ music).
"""
import argparse
import json
import os
import re
import time

from assets import get_visual, make_voice
from render import assemble, render_scene, write_srt
from script import write_script


def load_env():
    """Read KEY=value lines from the .env file next to this script."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        print(f"  warning: no .env found at {path}")
        return
    for line in open(path):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.strip().split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    found = [k for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "PIXABAY_API_KEY", "PEXELS_API_KEY")
             if os.getenv(k)]
    print(f"  keys loaded: {', '.join(found) or 'none'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--music", help="optional background track (mp3)")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()
    load_env()

    slug = re.sub(r"[^a-z0-9]+", "-", args.topic.lower()).strip("-")[:40]
    work = os.path.join(args.out, f"{slug}-{int(time.time())}")
    os.makedirs(work, exist_ok=True)
    t0 = time.time()

    print("1/4 writing script")
    script = write_script(args.topic)
    json.dump(script, open(os.path.join(work, "script.json"), "w"), indent=2)
    scenes = script["scenes"]

    scene_files, durations = [], []
    for i, scene in enumerate(scenes, 1):
        print(f"2-3/4 scene {i}/{len(scenes)}: {scene['search_query']}")
        base = os.path.join(work, f"scene{i:02}")
        secs = make_voice(scene["narration"], base + "_voice.mp3")
        visual = get_visual(scene["search_query"], base + "_visual", secs)
        render_scene(visual, base + "_voice.mp3", secs, base + ".mp4")
        scene_files.append(base + ".mp4")
        durations.append(secs)

    print("4/4 assembling")
    srt = os.path.join(work, "captions.srt")
    write_srt(scenes, durations, srt)
    final = os.path.join(work, f"{slug}.mp4")
    assemble(scene_files, srt, final, args.music)

    print(f"\nDone in {time.time() - t0:.0f}s -> {final} ({sum(durations):.0f}s of video)")


if __name__ == "__main__":
    main()
