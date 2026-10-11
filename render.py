"""Step 4: stitch everything into one mp4 with ffmpeg.

Each scene is rendered to an identical format (1920x1080, 30fps, h264/aac),
so the final concat is a cheap copy. Captions and music are added last.
"""
import os
import subprocess

W, H, FPS = 1920, 1080, 30
FIT = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def render_scene(visual: str, voice: str, seconds: float, out: str):
    if visual.endswith(".mp4"):
        # Loop the clip in case it's shorter than the narration, then trim.
        video_in = ["-stream_loop", "-1", "-i", visual]
        vf = f"{FIT},fps={FPS}"
    else:
        # Still image: slow Ken Burns zoom so it doesn't feel frozen.
        frames = int(seconds * FPS) + 1
        video_in = ["-loop", "1", "-i", visual]
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='min(zoom+0.0007,1.2)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':"
              f"d={frames}:s={W}x{H}:fps={FPS},setsar=1")
    ff(*video_in, "-i", voice, "-t", f"{seconds:.3f}",
       "-map", "0:v", "-map", "1:a", "-vf", vf,
       "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-ar", "44100", "-ac", "2", out)


def write_srt(scenes: list, durations: list, path: str, words_per_line: int = 6):
    """Split each scene's narration into short lines, timed by character length."""
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    entries, start = [], 0.0
    for scene, dur in zip(scenes, durations):
        words = scene["narration"].split()
        chunks = [" ".join(words[i:i + words_per_line]) for i in range(0, len(words), words_per_line)]
        total = sum(len(c) for c in chunks) or 1
        t = start
        for c in chunks:
            end = t + dur * len(c) / total
            entries.append(f"{len(entries) + 1}\n{ts(t)} --> {ts(end)}\n{c}\n")
            t = end
        start += dur
    with open(path, "w") as f:
        f.write("\n".join(entries))


def has_filter(name: str) -> bool:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return f" {name} " in out.stdout


def assemble(scene_files: list, srt: str, out: str, music: str | None = None):
    workdir = os.path.dirname(srt)
    listfile = os.path.join(workdir, "concat.txt")
    with open(listfile, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in scene_files)
    joined = os.path.join(workdir, "joined.mp4")
    ff("-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", joined)

    # Optional music bed: looped under the voice at low volume.
    inputs, audio = ["-i", joined], ["-map", "0:a", "-c:a", "copy"]
    if music and os.path.exists(music):
        inputs += ["-stream_loop", "-1", "-i", music]
        audio = ["-filter_complex",
                 "[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                 "-map", "[a]", "-c:a", "aac"]

    if has_filter("subtitles"):
        # Burn captions into the picture (needs ffmpeg built with libass).
        style = ("FontSize=16,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
                 "BorderStyle=1,Outline=2,Shadow=0,MarginV=40")
        ff(*inputs, "-map", "0:v", "-vf", f"subtitles={srt}:force_style='{style}'",
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", *audio, out)
    else:
        # Fallback: captions as a subtitle track players can toggle on (CC).
        print("  ffmpeg has no 'subtitles' filter -> adding captions as a CC track instead")
        srt_index = inputs.count("-i")  # the SRT is the next input after these
        ff(*inputs, "-i", srt, "-map", "0:v", "-map", f"{srt_index}:s",
           "-c:v", "copy", "-c:s", "mov_text", *audio, out)
