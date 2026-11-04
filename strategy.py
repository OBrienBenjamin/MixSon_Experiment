import argparse
import csv
import os
import re
import queue
import random
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from datetime import datetime
from itertools import combinations
from pathlib import Path

from appdir import app_dir, find_ffmpeg, probe_video, has_audio_stream

try:
    import pygame
except ImportError:
    raise SystemExit("Missing package: pygame. Install with:\n  pip install pygame")

# ---------------- configuration ----------------
HERE = app_dir()
MEDIA_DIR = HERE / "media" / "AV"                  # media/AV/<speed|synch>_<n>_<Strategy>.mp4
RESULTS_DIR = HERE / "Responses" / "Strategy"
EXT = ".mp4"
MODE = "both"                                      # every block is audiovisual
USE_PRACTICE = True
ALLOW_MISSING_AUDIO = False      # True = play clips without an audio track silently (testing only)

PARAMETERS = {
    "synch": {
        "task": "pairwise",
        "prefix": "synch",
        "suffix": "_Event",      # Audio/AV files: synch_<n>_Event (Video: synch_<n>)
        "clips_per_block": 6,    # test clips per block (practice files not counted)
        # "n_reps": 5,
        "train_ids": [0, 75, 350, 400],
        "practice_pairs": [(0, 75), (0, 350), (0, 400), (75, 350), (75, 400), (350, 400)],  # practice clips, played in this order
        "question": "Which service was had better synchronization?",
        "instructions": ("Welcome.\n\nIn each trial you will perceive two tennis services, one after the "
                         "other.\n\nAfter the second service, choose which one had better synchronization.\n\nPress 1 for the first service or 2 for the second "
                         "service.\n\nBefore each block you will do a short practice.\n\n"
                         "Press SPACE to begin."),
    },
    "speed": {
        "task": "pairwise",
        "prefix": "speed",
        "suffix": "_Step",     # files are named speed_<n>[_text]
        "clips_per_block": 6,    # -> 15 pairs x 2 orders = 30 trials per block
        "train_ids": [32, 34, 50, 53],
        "practice_pairs": [(32, 34), (32, 50), (32, 53), (34, 350), (34, 400), (350, 400)],     # one practice trial per pair, random AB/BA
        "question": "Which service was faster at the point of impact?",
        "instructions": ("Welcome.\n\nIn each trial you will perceive two services, one after the "
                         "other.\n\nAfter the second service, choose which one was faster at the "
                         "point of impact.\n\nPress 1 for the first service or 2 for the second "
                         "service.\n\nBefore each block you will do a short practice.\n\n"
                         "Press SPACE to begin."),
    },
}

SCALE_LABELS = {1: "Bad", 2: "Poor", 3: "Fair", 4: "Good", 5: "Excellent"}      # MOS (no longer in use)
CHOICE_LABELS = {1: "the FIRST", 2: "the SECOND"}                                # speed

ITI_MS = 500                     # fixation before each trial
CUE_MS = 500                     # speed only: "1" / "2" cue before each clip
ISI_MS = 1000                    # speed only: pause between the two clips

CANVAS = (1280, 720)             # render size; set to (1920, 1080) if your clips are 1080p and playback is smooth
QUEUE_FRAMES = 60                # decode-ahead buffer (frames)
PREBUFFER_FRAMES = 15            # frames to have ready before playback starts

MIXER_FREQ = 44100               # set to your files' sample rate (e.g. 48000) to avoid conversion
MIXER_BUFFER = 512               # smaller = lower audio latency

MOS_COLUMNS = ["participant", "parameter", "block", "phase", "stimulus", "repetition",
               "response", "status", "block_order_pos", "trial_in_block", "trial_global",
               "rt_after_playback_s", "timestamp"]
PAIRWISE_COLUMNS = ["participant", "parameter", "block", "phase", "first", "second", "pair",
                    "response", "chosen", "status", "block_order_pos", "trial_in_block",
                    "trial_global", "rt_after_playback_s", "timestamp"]
DESIGN_COLUMNS = ["participant", "parameter", "block_order_pos", "block", "phase",
                  "trial_in_block", "repetition", "stimulus_1", "stimulus_2"]
# ------------------------------------------------


class Abort(Exception):
    pass


def split_media(folder, ext, prefix, train_ids, suffix):
    """Find <prefix>_<n><suffix><ext> files in folder (case-insensitive).
    Files whose number is in train_ids are practice clips; the rest are test clips.
    Files with any other suffix (other strategies) are ignored.
    Returns (test_files, train_by_id)."""
    if not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")
    pat = re.compile(rf"^{re.escape(prefix)}_(\d+){re.escape(suffix)}$", re.IGNORECASE)
    test, train = [], {}
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() != ext:
            continue
        m = pat.match(p.stem)
        if not m:
            continue
        sid = int(m.group(1))
        if sid in train_ids:
            if sid in train:
                raise SystemExit(f"{folder}: two files match practice clip {prefix}_{sid}{suffix}: "
                                 f"{train[sid].name} and {p.name}")
            train[sid] = p
        else:
            test.append(p)
    return test, train


def build_mos_trials(files, n_reps, rng):
    """n_reps full permutations; avoid the same clip back-to-back across repetitions."""
    trials = []
    for rep in range(1, n_reps + 1):
        order = files[:]
        rng.shuffle(order)
        while trials and order[0] == trials[-1]["clips"][0]:
            rng.shuffle(order)
        trials.extend({"rep": rep, "clips": (f,)} for f in order)
    return trials


def build_pairwise_trials(files, rng):
    """All unordered pairs in both orders (AB and BA), shuffled; the two orders of the
    same pair never occur back to back."""
    pairs = list(combinations(files, 2))
    trials = [{"rep": "", "clips": (a, b)} for a, b in pairs]
    trials += [{"rep": "", "clips": (b, a)} for a, b in pairs]
    for _ in range(2000):
        rng.shuffle(trials)
        if all(frozenset(trials[i]["clips"]) != frozenset(trials[i + 1]["clips"])
               for i in range(len(trials) - 1)):
            break
    return trials


def pair_label(a, b):
    return " vs ".join(sorted([a.stem, b.stem]))


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
    def __init__(self, participant, parameter, seed=None, start_block=None):
        self.ffmpeg = find_ffmpeg()
        if not self.ffmpeg:
            raise SystemExit("ffmpeg not found. Run: pip install imageio-ffmpeg "
                            "(or place ffmpeg in a 'bin' folder next to the app).")

        self.participant = participant
        self.parameter = parameter
        self.cfg = PARAMETERS[parameter]
        self.kind = self.cfg["task"]                       # "mos" or "pairwise"
        self.rng = random.Random(seed)
        self.start_block = start_block

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"strategy_{self.kind}_{parameter}_{participant}_{stamp}"
        self.out_path = RESULTS_DIR / f"{prefix}.csv"
        self.design_path = RESULTS_DIR / f"{prefix}_design.csv"

        self.plan = self._make_plan()
        self._write_design()
        append_row_safely(self.out_path,
                          MOS_COLUMNS if self.kind == "mos" else PAIRWISE_COLUMNS)

        self.trial_global = 0
        self.cur = None
        self.block = None
        self.trial_open = False
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
        self.big_font = pygame.font.SysFont("helveticaneue,helvetica,arial", 160)
        self.clock = pygame.time.Clock()

    # ---------- planning ----------
    def _make_practice(self, train_by_id):
        if self.kind == "mos":
            return [{"rep": "", "clips": (train_by_id[i],)} for i in self.cfg["train_ids"]]

        # speed: one trial per configured pair, each in a random order (AB or BA)
        trials = []
        for a, b in self.cfg["practice_pairs"]:
            fa, fb = train_by_id[a], train_by_id[b]
            if self.rng.random() < 0.5:
                fa, fb = fb, fa
            trials.append({"rep": "", "clips": (fa, fb)})
        self.rng.shuffle(trials)                                   # random trial order too
        return trials

    def _make_plan(self):
        prefix = self.cfg["prefix"]
        block_names = list(self.cfg["strategies"])                 # one block per strategy
        self.rng.shuffle(block_names)
        if self.start_block:                                       # force this block to come first
            first = next(n for n in block_names if n.lower() == self.start_block)
            block_names.remove(first)
            block_names.insert(0, first)

        plan = []
        for pos, name in enumerate(block_names, 1):
            tsuffix = f"_{name}"
            test_files, train_by_id = split_media(MEDIA_DIR, EXT, prefix,
                                                  self.cfg["train_ids"], tsuffix)

            n = self.cfg["clips_per_block"]
            if len(test_files) != n:
                raise SystemExit(
                    f"{MEDIA_DIR}: block '{name}': expected {n} test files named "
                    f"{prefix}_<n>{tsuffix}{EXT}, found {len(test_files)}.\n"
                    f"(numbers in {self.cfg['train_ids']} are used for practice; "
                    f"other strategies are ignored)\n  "
                    + "\n  ".join(p.name for p in test_files))

            if self.kind == "mos":
                trials = build_mos_trials(test_files, self.cfg["n_reps"], self.rng)
            else:
                trials = build_pairwise_trials(test_files, self.rng)

            practice = []
            if USE_PRACTICE:
                missing = [f"{prefix}_{i}{tsuffix}{EXT}"
                           for i in self.cfg["train_ids"] if i not in train_by_id]
                if missing:
                    raise SystemExit(f"{MEDIA_DIR}: missing practice file(s): {', '.join(missing)}")
                practice = self._make_practice(train_by_id)

            plan.append({"pos": pos, "name": name, "mode": MODE,
                         "practice": practice, "trials": trials})
        return plan

    def _write_design(self):
        append_row_safely(self.design_path, DESIGN_COLUMNS)
        for b in self.plan:
            for phase, trials in (("practice", b["practice"]), ("test", b["trials"])):
                for i, t in enumerate(trials, 1):
                    clips = t["clips"]
                    append_row_safely(self.design_path, [
                        self.participant, self.parameter, b["pos"], b["name"], phase, i,
                        t["rep"] if phase == "test" else "",
                        clips[0].name, clips[1].name if len(clips) > 1 else ""])

    # ---------- stimulus preparation ----------
    def _prepare_audio(self, path):
        if wav_is_usable_directly(path):
            return pygame.mixer.Sound(str(path))
        if not has_audio_stream(self.ffmpeg, path):
            if ALLOW_MISSING_AUDIO:
                print(f"[warning] no audio track in {path}; it will play silently")
                return None
            raise SystemExit(f"No audio track found in: {path}\n"
                             "Re-export it with audio (needed for the audiovisual block), "
                             "or set ALLOW_MISSING_AUDIO = True to play it silently.")
        out = Path(self.tmpdir.name) / f"clip_{len(self.sounds)}.wav"   # unique name per clip
        subprocess.run([self.ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-vn",
                        "-ac", "2", "-ar", str(MIXER_FREQ), "-acodec", "pcm_s16le", str(out)],
                       check=True)
        return pygame.mixer.Sound(str(out))

    def _prepare_video(self, path):
        w, h, fps = probe_video(self.ffmpeg, path)
        scale = min(self.W / w, self.H / h)
        nw = max(2, int(w * scale) // 2 * 2)
        nh = max(2, int(h * scale) // 2 * 2)
        return {"w": nw, "h": nh, "fps": fps}

    def prepare(self):
        self.draw_text("Preparing stimuli…")
        for block in self.plan:
            files = []
            for t in block["practice"] + block["trials"]:
                files.extend(t["clips"])
            for f in sorted(set(files)):
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

    def draw_big(self, text):
        self.screen.fill((0, 0, 0))
        surf = self.big_font.render(text, True, (255, 255, 255))
        self.screen.blit(surf, ((self.W - surf.get_width()) // 2,
                                (self.H - surf.get_height()) // 2))
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
    def play_clip(self, file, mode, label=None):
        """Play one clip. `label` ("1"/"2") is shown during audio-only clips (speed task)."""
        use_video = mode in ("video", "both")
        use_audio = mode in ("audio", "both") and self.sounds.get(file) is not None
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
                font = self.big_font if label else self.font
                surf = font.render(label or "+", True, (255, 255, 255))
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

    # ---------- responses ----------
    def get_rating(self):
        scale = "     ".join(f"{k} = {v}" for k, v in SCALE_LABELS.items())
        self.draw_text(f"{self.cfg['question']}\n\n{scale}")
        pygame.event.clear()
        t_start = time.perf_counter()
        while True:
            for e in self.pump():
                if e.unicode and e.unicode in "12345":
                    return int(e.unicode), time.perf_counter() - t_start
            self.clock.tick(120)

    def get_choice(self):
        self.draw_text(f"{self.cfg['question']}\n\n"
                       f"1 = {CHOICE_LABELS[1]}          2 = {CHOICE_LABELS[2]}")
        pygame.event.clear()
        t_start = time.perf_counter()
        while True:
            for e in self.pump():
                if e.unicode in ("1", "2"):
                    return int(e.unicode), time.perf_counter() - t_start
            self.clock.tick(120)

    # ---------- trial / main flow ----------
    def run_trial(self, trial, phase, idx):
        mode = self.block["mode"]
        if phase == "test":
            self.trial_global += 1
        self.cur = {"phase": phase, "trial": idx, "rep": trial["rep"],
                    "clips": trial["clips"],
                    "global": self.trial_global if phase == "test" else ""}
        self.trial_open = True

        self.draw_text("+")
        self.wait_ms(ITI_MS)

        if self.kind == "mos":
            self.play_clip(trial["clips"][0], mode)
            response, rt = self.get_rating()
        else:
            first, second = trial["clips"]
            self.draw_big("1")
            self.wait_ms(CUE_MS)
            self.play_clip(first, mode, "1")
            self.draw_text("+")
            self.wait_ms(ISI_MS)
            self.draw_big("2")
            self.wait_ms(CUE_MS)
            self.play_clip(second, mode, "2")
            response, rt = self.get_choice()

        self.save(response, "completed", rt)
        self.trial_open = False

    def run(self):
        try:
            self.prepare()
            self.wait_space(self.cfg["instructions"])
            n_blocks = len(self.plan)
            for bi, block in enumerate(self.plan):
                self.block = block
                if block["practice"]:
                    self.wait_space(f"Block {bi + 1} of {n_blocks}.\n\n"
                                    f"First, {len(block['practice'])} practice trials to get used "
                                    "to the task. They are not part of the test.\n\n"
                                    "Press SPACE to start the practice.")
                    for i, trial in enumerate(block["practice"], 1):
                        self.run_trial(trial, "practice", i)
                    self.wait_space("Practice finished.\n\nThe test block starts now.\n\n"
                                    "Press SPACE to continue.")
                else:
                    self.wait_space(f"Block {bi + 1} of {n_blocks}.\n\nPress SPACE to begin.")

                for i, trial in enumerate(block["trials"], 1):
                    self.run_trial(trial, "test", i)

                if bi < n_blocks - 1:
                    self.wait_space(f"Block {bi + 1} of {n_blocks} complete.\n\n"
                                    "Take a short break.\nPress SPACE to continue.")
            self.wait_space("Experiment finished. Thank you!\n\nPress SPACE to exit.")
        except Abort:
            pass
        finally:
            self.shutdown()

    # ---------- saving / shutdown ----------
    def save(self, response, status, rt=None):
        c = self.cur
        is_test = c["phase"] == "test"
        rt_s = "" if rt is None else f"{rt:.3f}"
        ts = datetime.now().isoformat(timespec="seconds")
        if self.kind == "mos":
            row = [self.participant, self.parameter, self.block["name"], c["phase"],
                   c["clips"][0].name, c["rep"] if is_test else "", response, status,
                   self.block["pos"], c["trial"], c["global"], rt_s, ts]
        else:
            first, second = c["clips"]
            chosen = "" if response == "" else (first if response == 1 else second).name
            row = [self.participant, self.parameter, self.block["name"], c["phase"],
                   first.name, second.name, pair_label(first, second), response, chosen,
                   status, self.block["pos"], c["trial"], c["global"], rt_s, ts]
        append_row_safely(self.out_path, row)

    def shutdown(self):
        try:
            if self.trial_open and self.cur is not None:
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
    ap.add_argument("--parameter", required=True, type=str.lower, choices=sorted(PARAMETERS),
                    help="synch = MOS rating test; speed = pairwise comparison test")
    ap.add_argument("--start-block", type=str.lower, default=None,
                    help="strategy block to run first (speed: step, osc, bpf; "
                         "synch: event, static, centroid); the others stay in random order")
    ap.add_argument("--seed", type=int, default=None, help="optional, for reproducible order")
    args = ap.parse_args()

    valid = [s.lower() for s in PARAMETERS[args.parameter]["strategies"]]
    if args.start_block and args.start_block not in valid:
        ap.error(f"--start-block for '{args.parameter}' must be one of: {', '.join(valid)}")

    Experiment(args.participant, args.parameter, args.seed, args.start_block).run()