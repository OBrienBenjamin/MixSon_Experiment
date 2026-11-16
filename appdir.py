"""Helpers shared by the launcher and the experiment scripts."""
import os
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

# Windows: do not open a console window for every ffmpeg call (a windowed app has no console).
# On macOS/Linux this is 0, which means "no special flags".
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_quiet(cmd, **kwargs):
    """subprocess.run that also works inside a windowed (no console) Windows app:
    stdin is never inherited and no console window is created."""
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(cmd, **kwargs)


def popen_quiet(cmd, **kwargs):
    """subprocess.Popen with the same safeguards as run_quiet."""
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.Popen(cmd, **kwargs)


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


@lru_cache(maxsize=None)
def _stream_info(ffmpeg, path):
    """Text printed by `ffmpeg -i <file>` (it lists the streams, then exits with an
    'at least one output file' error, which is expected). Cached: one call per file,
    shared by probe_video and has_audio_stream. A hung ffmpeg raises after 60 s
    instead of freezing the app."""
    out = run_quiet([ffmpeg, "-nostdin", "-hide_banner", "-i", str(path)],
                    capture_output=True, text=True, errors="replace", timeout=60)
    return out.stderr


def probe_video(ffmpeg, path):
    """Return (width, height, fps) of the first video stream."""
    info = _stream_info(ffmpeg, str(path))
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
               for l in _stream_info(ffmpeg, str(path)).splitlines())