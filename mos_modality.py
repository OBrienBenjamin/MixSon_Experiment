import argparse
import csv
import os
import queue
import random
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

try:
    import pygame
except ImportError:
    raise SystemExit("Missing package: pygame. Install with:\n  pip install pygame")

# ---------------- configuration ----------------
MEDIA_ROOT = Path(os.path.join("media", "MOS", "Modality"))
TRAIN_ROOT = Path(os.path.join(MEDIA_ROOT, "Train"))      # Train/Audio, Train/Video, Train/AV
RESULTS_DIR = Path(os.path.join("Responses", "MOS", "Modality"))
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

BLOCKS = {                       # block name -> (folder, mode); same folder names in MEDIA_ROOT and TRAIN_ROOT
    "Audio":       ("Audio", "audio"),
    "Video":       ("Video", "video"),
    "Audiovisual": ("AV",    "both"),
}
N_REPS = 1
CLIPS_PER_BLOCK = 8
N_PRACTICE = 2                   # practice clips shown before each block (played in sorted filename order)
ITI_MS = 500
EXTENSIONS = {".mp4", ".mov", ".wav"}

CANVAS = (1280, 720)             # render size; set to (1920, 1080) if your clips are 1080p and playback is smooth
QUEUE_FRAMES = 60                # decode-ahead buffer (frames)
PREBUFFER_FRAMES = 15            # frames to have ready before playback starts

MIXER_FREQ = 44100               # set to your files' sample rate (e.g. 48000) to avoid conversion
MIXER_BUFFER = 512               # smaller = lower audio latency

QUESTION = "How would you rate the quality of what you just experienced?"
SCALE_LABELS = {1: "Bad", 2: "Poor", 3: "Fair", 4: "Good", 5: "Excellent"}

RESULT_COLUMNS = ["participant", "block", "phase", "stimulus", "repetition", "response",
                  "status", "block_order_pos", "trial_in_block", "trial_global",
                  "rt_after_playback_s", "timestamp"]
DESIGN_COLUMNS = ["participant", "block_order_pos", "block", "phase",
                  "trial_in_block", "repetition", "stimulus"]
# ------------------------------------------------

class Abort(Exception):
    pass

def list_media(folder, expected):
    """Sorted media files in folder; exits with a clear message if missing or wrong count."""
    if not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in EXTENSIONS)
    if len(files) != expected:
        raise SystemExit(f"{folder}: expected {expected} files, found {len(files)}")
    return files


def build_block_trials(files, n_reps, rng):
    trials = []
    for rep in range(1, n_reps + 1):
        order = files[:]
        rng.shuffle(order)
        while trials and order[0] == trials[-1][1]:
            rng.shuffle(order)
        trials.extend((rep, f) for f in order)
    return trials


def append_row_safely(path, row):
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow(row)
        f.flush()
        os.fsync(f.fileno())


def wav_is_usable_directly(path):
    if path.suffix.lower() != ".wav":
        return False
    try:
        with wave.open(str(path), "rb") as w:
            return w.getsampwidth() == 2 and w.getframerate() == MIXER_FREQ
    except Exception:
        return False


def probe_video(ffprobe, path):
    """Return (width, height, fps) of the first video stream."""
    out = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    try:
        w, h, rate = out.stdout.strip().split(",")[:3]
        num, _, den = rate.partition("/")
        fps = float(num) / float(den or 1)
        if fps <= 0:
            fps = 25.0
        return int(w), int(h), fps
    except Exception:
        raise SystemExit(f"Could not read video info from {path}\n{out.stderr}")


def frame_reader(proc, frame_bytes, q, stop, done):
    """Background thread: read raw frames from ffmpeg into a bounded queue."""
    try:
        while not stop.is_set():
            d = proc.stdout.read(frame_bytes)
            if len(d) < frame_bytes:
                break
            while not stop.is_set():
                try:
                    q.put(d, timeout=0.05)
                    break
                except queue.Full:
                    continue
    finally:
        done.set()


class Experiment:
    def __init__(self, participant, seed=None):
        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")
        if not (self.ffmpeg and self.ffprobe):
            raise SystemExit("ffmpeg/ffprobe not found on PATH. Activate your conda env or:\n"
                             "  conda install -c conda-forge ffmpeg")

        self.participant = participant
        self.rng = random.Random(seed)
        RESULTS_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.out_path = RESULTS_DIR / f"mos_modality_{participant}_{stamp}.csv"
        self.design_path = RESULTS_DIR / f"mos_modality_{participant}_{stamp}_design.csv"

        self.plan = self._make_plan()
        self._write_design()
        append_row_safely(self.out_path, RESULT_COLUMNS)

        self.trial_global = 0
        self.trial_idx = 0
        self.trial_open = False
        self.phase = "test"
        self.sounds = {}
        self.video_info = {}
        self.tmpdir = tempfile.TemporaryDirectory()

        pygame.mixer.pre_init(MIXER_FREQ, -16, 2, MIXER_BUFFER)
        pygame.init()
        pygame.mixer.set_num_channels(2)
        flags = pygame.SCALED | pygame.FULLSCREEN
        try:
            self.screen = pygame.display.set_mode(CANVAS, flags, vsync=1)
        except pygame.error:
            self.screen = pygame.display.set_mode(CANVAS, flags)
        pygame.display.set_caption("Experiment")
        pygame.mouse.set_visible(False)
        self.W, self.H = CANVAS
        self.font = pygame.font.SysFont("helveticaneue,helvetica,arial", 40)
        self.clock = pygame.time.Clock()

    # ---------- planning ----------
    def _make_plan(self):
        block_names = list(BLOCKS)
        self.rng.shuffle(block_names)
        plan = []
        for pos, name in enumerate(block_names, 1):
            folder, mode = BLOCKS[name]
            files = list_media(MEDIA_ROOT / folder, CLIPS_PER_BLOCK)
            practice = list_media(TRAIN_ROOT / folder, N_PRACTICE)
            plan.append({"pos": pos, "name": name, "mode": mode,
                         "practice": practice,
                         "trials": build_block_trials(files, N_REPS, self.rng)})
        return plan

    def _write_design(self):
        append_row_safely(self.design_path, DESIGN_COLUMNS)
        for b in self.plan:
            for i, f in enumerate(b["practice"], 1):
                append_row_safely(self.design_path,
                                  [self.participant, b["pos"], b["name"], "practice",
                                   i, "", f.name])
            for i, (rep, f) in enumerate(b["trials"], 1):
                append_row_safely(self.design_path,
                                  [self.participant, b["pos"], b["name"], "test",
                                   i, rep, f.name])

    # ---------- stimulus preparation ----------
    def _prepare_audio(self, path):
        if wav_is_usable_directly(path):
            return pygame.mixer.Sound(str(path))
        out = Path(self.tmpdir.name) / f"clip_{len(self.sounds)}.wav"   # unique name per clip
        subprocess.run([self.ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-vn",
                        "-ac", "2", "-ar", str(MIXER_FREQ), "-acodec", "pcm_s16le", str(out)],
                       check=True)
        return pygame.mixer.Sound(str(out))

    def _prepare_video(self, path):
        w, h, fps = probe_video(self.ffprobe, path)
        scale = min(self.W / w, self.H / h)
        nw = max(2, int(w * scale) // 2 * 2)
        nh = max(2, int(h * scale) // 2 * 2)
        return {"w": nw, "h": nh, "fps": fps}

    def prepare(self):
        self.draw_text("Preparing stimuli…")
        for block in self.plan:
            files = block["practice"] + [f for _, f in block["trials"]]
            for f in files:
                if block["mode"] in ("audio", "both") and f not in self.sounds:
                    self.sounds[f] = self._prepare_audio(f)
                if block["mode"] in ("video", "both") and f not in self.video_info:
                    self.video_info[f] = self._prepare_video(f)
                self.pump()

    # ---------- drawing / input ----------
    def wrap(self, text):
        words, lines, cur = text.split(" "), [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if self.font.size(test)[0] <= self.W * 0.8:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    def draw_text(self, text):
        self.screen.fill((0, 0, 0))
        lines = []
        for para in text.split("\n"):
            lines += self.wrap(para) if para else [""]
        lh = self.font.get_linesize()
        y = (self.H - lh * len(lines)) // 2
        for ln in lines:
            surf = self.font.render(ln, True, (255, 255, 255))
            self.screen.blit(surf, ((self.W - surf.get_width()) // 2, y))
            y += lh
        pygame.display.flip()

    def pump(self):
        keys = []
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                raise Abort
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    raise Abort
                keys.append(e)
        return keys

    def wait_space(self, text):
        self.draw_text(text)
        pygame.event.clear()
        while True:
            if any(e.key == pygame.K_SPACE for e in self.pump()):
                return
            self.clock.tick(60)

    def wait_ms(self, ms):
        end = time.perf_counter() + ms / 1000
        while time.perf_counter() < end:
            self.pump()
            self.clock.tick(120)

    # ---------- playback ----------
    def play_clip(self, file, mode):
        use_video = mode in ("video", "both")
        use_audio = mode in ("audio", "both")
        proc = reader = channel = None
        stop, done = threading.Event(), threading.Event()
        q = queue.Queue(maxsize=QUEUE_FRAMES)

        try:
            self.screen.fill((0, 0, 0))
            if use_video:
                info = self.video_info[file]
                fps, nw, nh = info["fps"], info["w"], info["h"]
                frame_bytes = nw * nh * 3
                pos = ((self.W - nw) // 2, (self.H - nh) // 2)
                proc = subprocess.Popen(
                    [self.ffmpeg, "-loglevel", "error", "-i", str(file), "-an",
                     "-vf", f"fps={fps:.6f},scale={nw}:{nh}:flags=bilinear",
                     "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    bufsize=frame_bytes * 2)
                reader = threading.Thread(target=frame_reader,
                                          args=(proc, frame_bytes, q, stop, done),
                                          daemon=True)
                reader.start()

                # wait for a small buffer before starting
                t_wait = time.perf_counter()
                while (q.qsize() < PREBUFFER_FRAMES and not done.is_set()
                       and time.perf_counter() - t_wait < 3):
                    self.pump()
                    time.sleep(0.005)
                try:
                    first = q.get(timeout=2)
                except queue.Empty:
                    raise SystemExit(f"Could not decode video: {file}")
                self.screen.blit(pygame.image.frombuffer(first, (nw, nh), "RGB"), pos)
            else:
                fps = 25.0
                surf = self.font.render("+", True, (255, 255, 255))
                self.screen.blit(surf, ((self.W - surf.get_width()) // 2,
                                        (self.H - surf.get_height()) // 2))
            pygame.display.flip()

            # audio and clock start once the first frame is on screen
            if use_audio:
                channel = pygame.mixer.Channel(0)
                channel.play(self.sounds[file])
            t0 = time.perf_counter()
            frame_idx = 0
            video_done = not use_video

            while True:
                self.pump()
                audio_done = (channel is None) or (not channel.get_busy())
                if not video_done:
                    target = int((time.perf_counter() - t0) * fps)
                    data = None
                    while frame_idx < target:
                        try:
                            data = q.get_nowait()
                            frame_idx += 1
                        except queue.Empty:
                            break
                    if data is not None:
                        self.screen.blit(pygame.image.frombuffer(data, (nw, nh), "RGB"), pos)
                        pygame.display.flip()
                    elif done.is_set() and q.empty():
                        video_done = True
                if video_done and audio_done:
                    break
                self.clock.tick(240)
        finally:
            stop.set()
            if proc is not None:
                proc.kill()
                proc.wait()
            if reader is not None:
                reader.join(timeout=1)
            if channel is not None:
                channel.stop()

    def get_rating(self):
        scale = "     ".join(f"{k} = {v}" for k, v in SCALE_LABELS.items())
        self.draw_text(f"{QUESTION}\n\n{scale}")
        pygame.event.clear()
        t_start = time.perf_counter()
        while True:
            for e in self.pump():
                if e.unicode and e.unicode in "12345":
                    return int(e.unicode), time.perf_counter() - t_start
            self.clock.tick(120)

    # ---------- main flow ----------
    def run_trial(self, file, mode, phase, rep, idx):
        self.file, self.rep, self.trial_idx, self.phase = file, rep, idx, phase
        if phase == "test":
            self.trial_global += 1
        self.trial_open = True
        self.draw_text("+")
        self.wait_ms(ITI_MS)
        self.play_clip(file, mode)
        rating, rt = self.get_rating()
        self.save(rating, "completed", rt)
        self.trial_open = False

    def run(self):
        try:
            self.prepare()
            self.wait_space("Welcome.\n\nEach clip plays automatically. When it ends, rate it "
                            "from 1 to 5 using the keyboard.\n\nBefore each block you will see "
                            f"{N_PRACTICE} practice examples.\n\nPress SPACE to begin.")
            for bi, block in enumerate(self.plan):
                self.block = block

                # ---- practice ----
                self.wait_space(f"Block {bi + 1} of {len(self.plan)}.\n\n"
                                f"First, {N_PRACTICE} practice examples to get used to the task. "
                                "They are not part of the test.\n\nPress SPACE to start the practice.")
                for i, file in enumerate(block["practice"], 1):
                    self.run_trial(file, block["mode"], "practice", "", i)
                self.wait_space("Practice finished.\n\nThe test block starts now.\n\n"
                                "Press SPACE to continue.")

                # ---- test ----
                for i, (rep, file) in enumerate(block["trials"], 1):
                    self.run_trial(file, block["mode"], "test", rep, i)

                if bi < len(self.plan) - 1:
                    self.wait_space(f"Block {bi + 1} of {len(self.plan)} complete.\n\n"
                                    "Take a short break.\nPress SPACE to continue.")
            self.wait_space("Experiment finished. Thank you!\n\nPress SPACE to exit.")
        except Abort:
            pass
        finally:
            self.shutdown()

    # ---------- saving / shutdown ----------
    def save(self, response, status, rt=None):
        is_test = self.phase == "test"
        append_row_safely(self.out_path, [
            self.participant, self.block["name"], self.phase, self.file.name,
            self.rep if is_test else "", response,
            status, self.block["pos"], self.trial_idx,
            self.trial_global if is_test else "",
            "" if rt is None else f"{rt:.3f}",
            datetime.now().isoformat(timespec="seconds")])

    def shutdown(self):
        try:
            if self.trial_open:
                self.save("", "aborted")
                self.trial_open = False
        except Exception:
            pass
        try:
            pygame.mixer.stop()
            pygame.quit()
        except Exception:
            pass
        try:
            self.tmpdir.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--participant", required=True)
    ap.add_argument("--seed", type=int, default=None, help="optional, for reproducible order")
    args = ap.parse_args()
    Experiment(args.participant, args.seed).run()