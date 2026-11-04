"""Helpers shared by the launcher and both experiment scripts."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def app_dir():
    """Folder that holds media/ and Responses/: the repo folder when running from source,
    the folder next to the app when running a packaged build."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if exe.parent.name == "MacOS" and exe.parents[1].name == "Contents":
            return exe.parents[2].parent          # the folder that contains MixSon.app
        return exe.parent
    return Path(__file__).resolve().parent


def find_ffmpeg():
    """ffmpeg executable: bin/ folder next to the app, then the imageio-ffmpeg copy, then PATH."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    local = app_dir() / "bin" / exe
    if local.exists():
        return str(local)
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and Path(path).exists():
            return path
    except Exception:
        pass
    return shutil.which("ffmpeg")


def _stream_info(ffmpeg, path):
    """Text printed by `ffmpeg -i <file>` (it lists the streams, then exits with an
    'at least one output file' error, which is expected)."""
    out = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)],
                         capture_output=True, text=True, errors="replace")
    return out.stderr


def probe_video(ffmpeg, path):
    """Return (width, height, fps) of the first video stream."""
    info = _stream_info(ffmpeg, path)
    for line in info.splitlines():
        if "Stream #" in line and "Video:" in line:
            m = re.search(r"[\s,](\d{2,5})x(\d{2,5})[\s,\[]", line)
            if not m:
                break
            f = re.search(r"([\d.]+) fps", line) or re.search(r"([\d.]+) tbr", line)
            fps = float(f.group(1)) if f else 25.0
            return int(m.group(1)), int(m.group(2)), (fps if fps > 0 else 25.0)
    raise SystemExit(f"Could not read video info from {path}\n{info[-400:]}")


def has_audio_stream(ffmpeg, path):
    return any("Stream #" in l and "Audio:" in l
               for l in _stream_info(ffmpeg, path).splitlines())