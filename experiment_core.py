"""Shared code of the two experiments (modality.py and strategy.py).

Task: two-alternative forced choice. Each trial plays two clips one after the other
(first / second) and the participant says which one has the better synchronisation
(parameter "synch") or the higher racket-head speed at impact (parameter "speed").

Supported pair versions:
- "v1" (legacy): every TEST item is compared with every FOIL item (5 x 5 = 25 pairs),
  each in both orders (AB and BA) -> 50 trials; practice uses foil-only combinations.
- "v2" (explicit pairs): no test/foil logic. Uses explicit pairs per parameter shown
  in both orders (AB and BA) -> 50 trials, and fixed practice pairs from excluded stimuli
  that never overlap with test pairs (shown in a fixed order across participants).
"""
import argparse
import csv
import os
import queue
import random
import re
import subprocess
import tempfile
import threading
import time
import wave
from collections import namedtuple
from datetime import datetime
from itertools import combinations
from pathlib import Path

from appdir import (app_dir, find_ffmpeg, probe_video, has_audio_stream,
                    run_quiet, popen_quiet)

try:
    import pygame
except ImportError:
    raise SystemExit("Missing package: pygame. Install with:\n  pip install pygame")

# ---------------- configuration ----------------
HERE = app_dir()
MEDIA_ROOT = HERE / "media"

USE_PRACTICE = True
PRACTICE_MIN = 5                 # practice trials before the participant may skip to the test
ALLOW_MISSING_AUDIO = False      # True = play clips without an audio track silently (testing only)

DEFAULT_PAIR_VERSION = "v1"

_PAGE_ANSWER = ("Si vous pensez que c'est le service 1, tapez 1.\n\n"
                "Si vous pensez que c'est le service 2, tapez 2.")
_PAGE_PRACTICE = ("Avant chaque bloc expérimental, un court entrainement avec des services qui ne seront pas "
                  "présentés pendant les essais expérimentaux, vous sera proposé afin de vous familiariser "
                  "avec les consignes et avec les modalités de réponse.")

_PARAMETER_TEXTS = {
    "synch": {
        "prefix": "synch",
        "question": "Quel service présente, selon vous,\nla meilleure synchronisation entre \n"
                    "la flexion maximale du genou et \nla position verticale maximale de la tête de raquette ?",
        "instructions": [
            ("Pour chaque essai expérimental, deux services vous seront successivement présentés.\n\n"
             "Après avoir visionné le second service,\nvous devrez dire lequel des deux présentait\n"
             "la meilleure synchronisation temporelle entre\n"
             "la flexion maximale du genou et\n la position verticale maximale de la tête de raquette."),
            _PAGE_ANSWER,
            _PAGE_PRACTICE,
        ],
    },
    "speed": {
        "prefix": "speed",
        "question": "Quel service a la vitesse de tête de raquette à l'impact la plus élevée ?",
        "instructions": [
            ("Pour chaque essai expérimental, deux services vous seront successivement présentés.\n\n"
             "Après avoir visionné le second service, vous devrez dire lequel des deux présentait "
             "la vitesse de tête de raquette la plus élevée au moment de l'impact avec la balle."),
            _PAGE_ANSWER,
            _PAGE_PRACTICE,
        ],
    },
}

# Explicit pair lists for v2 (25 pairs each; shown in both AB and BA orders = 50 trials)
V2_SYNCH_PAIRS = [
    (0, 50),
    (50, 100),
    (100, 150),
    (200, 240),
    (350, 400),
    (0, 100),
    (50, 150),
    (200, 300),
    (240, 350),
    (300, 400),
    (0, 150),
    (50, 200),
    (150, 300),
    (200, 350),
    (240, 400),
    (0, 200),
    (50, 240),
    (100, 300),
    (150, 350),
    (200, 400),
    (0, 240),
    (0, 240),
    (50, 300),
    (100, 350),
    (150, 400),
]

V2_SPEED_PAIRS = [
    (37, 39),
    (39, 41),
    (41, 43),
    (43, 45),
    (45, 47),
    (37, 41),
    (37, 41),
    (39, 43),
    (41, 45),
    (43, 47),
    (37, 43),
    (39, 45),
    (39, 45),
    (41, 47),
    (47, 53),
    (37, 45),
    (39, 47),
    (39, 47),
    (45, 53),
    (45, 53),
    (37, 47),
    (37, 47),
    (43, 53),
    (43, 53),
    (43, 53),
]

# Fixed practice pairs for v2 (excluded stimuli strictly non-overlapping with test pairs)
V2_FIXED_PRACTICE_PAIRS = {
    "synch": [
        (0, 75),
        (75, 0),
        (0, 75),
        (75, 0),
        (0, 75),
        (75, 0),
    ],
    "speed": [
        (32, 34),
        (34, 50),
        (50, 32),
        (32, 50),
        (34, 32),
        (50, 34),
    ],
}

PAIR_VERSIONS = {
    "v1": {
        "mode": "grid",
        "parameters": {
            "synch": {
                **_PARAMETER_TEXTS["synch"],
                "test_ids": [50, 100, 150, 240, 350],
                "foil_ids": [0, 75, 200, 300, 400],
            },
            "speed": {
                **_PARAMETER_TEXTS["speed"],
                "test_ids": [34, 39, 41, 45, 50],
                "foil_ids": [32, 37, 43, 47, 53],
            },
        },
    },
    "v2": {
        "mode": "explicit_pairs",
        "parameters": {
            "synch": {
                **_PARAMETER_TEXTS["synch"],
                "pairs": V2_SYNCH_PAIRS,
                "practice_pairs": V2_FIXED_PRACTICE_PAIRS["synch"],
            },
            "speed": {
                **_PARAMETER_TEXTS["speed"],
                "pairs": V2_SPEED_PAIRS,
                "practice_pairs": V2_FIXED_PRACTICE_PAIRS["speed"],
            },
        },
    },
}

# Alias default version for backward compatibility
PARAMETERS = PAIR_VERSIONS[DEFAULT_PAIR_VERSION]["parameters"]

CHOICE_LABELS = {1: "le PREMIER", 2: "le DEUXIÈME"}

ITI_MS = 500                     # fixation before each trial
CUE_MS = 500                     # "1" / "2" cue before each clip
ISI_MS = 1000                    # pause between the two clips

CANVAS = (1280, 720)             # render size
QUEUE_FRAMES = 60                # decode-ahead buffer (frames)
PREBUFFER_FRAMES = 15            # frames to have ready before playback starts

MIXER_FREQ = 44100               # sample rate
MIXER_BUFFER = 512               # buffer size

RESULT_COLUMNS = ["participant", "age", "sex", "level", "parameter", "pair_version",
                  "block", "phase", "first", "second", "pair", "response", "chosen", "status",
                  "block_order_pos", "trial_in_block", "trial_global",
                  "rt_after_playback_s", "timestamp",
                  "first_id", "second_id", "test_id", "foil_id", "chosen_id", "chosen_role"]
DESIGN_COLUMNS = ["participant", "age", "sex", "level", "parameter", "pair_version",
                  "block_order_pos", "block", "phase", "trial_in_block", "first", "second",
                  "first_id", "second_id", "test_id", "foil_id"]

# Validate configuration structures on import
for _vname, _vcfg in PAIR_VERSIONS.items():
    for _pname, _pcfg in _vcfg["parameters"].items():
        if _vcfg["mode"] == "grid":
            _both = set(_pcfg["test_ids"]) & set(_pcfg["foil_ids"])
            if _both:
                raise ValueError(f"PAIR_VERSIONS['{_vname}']['{_pname}']: ids in both test and foil sets: {sorted(_both)}")
        elif _vcfg["mode"] == "explicit_pairs":
            _test_set = {frozenset((a, b)) for a, b in _pcfg["pairs"]}
            for a, b in _pcfg["pairs"]:
                if a == b:
                    raise ValueError(f"PAIR_VERSIONS['{_vname}']['{_pname}']: identical stimuli in pair ({a}, {b})")
            for a, b in _pcfg.get("practice_pairs", []):
                if a == b:
                    raise ValueError(f"PAIR_VERSIONS['{_vname}']['{_pname}']: identical stimuli in practice pair ({a}, {b})")
                if frozenset((a, b)) in _test_set:
                    raise ValueError(
                        f"PAIR_VERSIONS['{_vname}']['{_pname}']: practice pair ({a}, {b}) overlaps with a test pair"
                    )

Item = namedtuple("Item", "id role path")      # role: "test", "foil", "experimental", or "practice"


class Abort(Exception):
    pass


# ---------- stimuli and trial lists ----------
def find_media(folder, ext, prefix, suffix, ids):
    if not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")
    ids_set = set(ids)
    pat = re.compile(rf"^{re.escape(prefix)}_(\d+){re.escape(suffix)}$", re.IGNORECASE)
    found = {}
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() != ext:
            continue
        m = pat.match(p.stem)
        if not m or int(m.group(1)) not in ids_set:
            continue
        sid = int(m.group(1))
        if sid in found:
            raise SystemExit(f"{folder}: two files match {prefix}_{sid}{suffix}{ext}: "
                             f"{found[sid].name} and {p.name}")
        found[sid] = p
    missing = [f"{prefix}_{i}{suffix}{ext}" for i in ids if i not in found]
    if missing:
        raise SystemExit(f"{folder}: missing file(s): {', '.join(missing)}")
    return found


def _same_pair(t1, t2):
    return {t1[0].id, t1[1].id} == {t2[0].id, t2[1].id}


def build_test_trials(test_items, foil_items, rng):
    """v1: Every test item against every foil item in both orders (AB and BA)."""
    trials = []
    for t in test_items:
        for f in foil_items:
            trials.append((t, f))
            trials.append((f, t))
    for _ in range(2000):
        rng.shuffle(trials)
        if all(not _same_pair(trials[i], trials[i + 1]) for i in range(len(trials) - 1)):
            break
    return trials


def build_explicit_test_trials(pair_tuples, items_by_id, rng):
    """v2: Build both orders (AB and BA) for explicit pairs without test/foil classification."""
    trials = []
    for a_id, b_id in pair_tuples:
        a = items_by_id[a_id]
        b = items_by_id[b_id]
        trials.append((a, b))
        trials.append((b, a))
    for _ in range(2000):
        rng.shuffle(trials)
        if all(not _same_pair(trials[i], trials[i + 1]) for i in range(len(trials) - 1)):
            break
    return trials


def build_practice_trials(foil_items, rng):
    """v1: Practice combinations using foil items only."""
    pairs = list(combinations(foil_items, 2))
    rng.shuffle(pairs)
    first = [(a, b) if rng.random() < 0.5 else (b, a) for a, b in pairs]
    second = [(b, a) for a, b in first]
    for _ in range(100):
        rng.shuffle(second)
        if not _same_pair(first[-1], second[0]):
            break
    return first + second


def build_fixed_practice_trials(practice_pairs, items_by_id):
    """v2: Fixed practice trials across all participants."""
    return [(items_by_id[a_id], items_by_id[b_id]) for a_id, b_id in practice_pairs]


def test_foil_ids(first, second):
    """Return (test_id, foil_id) for v1 grid trials; ('', '') for v2 or practice pairs."""
    roles = {first.role, second.role}
    if roles != {"test", "foil"}:
        return "", ""
    test, foil = (first, second) if first.role == "test" else (second, first)
    return test.id, foil.id


def pair_label(a, b):
    return " vs ".join(sorted([a.path.stem, b.path.stem]))


def append_row_safely(path, row):
    with open(path, "a", newline="", encoding="utf-8") as f:
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


class BaseExperiment:
    results_dir = None

    @classmethod
    def block_names(cls, parameter):
        raise NotImplementedError

    def locate(self, name):
        raise NotImplementedError

    def __init__(self, participant, age, sex, level, parameter, seed=None, start_block=None,
                 pair_version=DEFAULT_PAIR_VERSION):
        self.ffmpeg = find_ffmpeg()
        if not self.ffmpeg:
            raise SystemExit("ffmpeg not found. Run: pip install imageio-ffmpeg "
                             "(or place ffmpeg in a 'bin' folder next to the app).")

        if pair_version not in PAIR_VERSIONS:
            raise ValueError(f"Unknown pair_version '{pair_version}'. Expected one of: {sorted(PAIR_VERSIONS)}")

        self.participant = participant
        self.age = age
        self.sex = sex
        self.level = level
        self.parameter = parameter
        self.pair_version = pair_version
        self.version_cfg = PAIR_VERSIONS[pair_version]
        self.cfg = self.version_cfg["parameters"][parameter]

        if self.version_cfg["mode"] == "grid":
            self.all_ids = list(dict.fromkeys(self.cfg["test_ids"] + self.cfg["foil_ids"]))
        else:
            exp_ids = [sid for pair in self.cfg["pairs"] for sid in pair]
            prac_ids = [sid for pair in self.cfg.get("practice_pairs", []) for sid in pair]
            self.all_ids = list(dict.fromkeys(exp_ids + prac_ids))

        self.rng = random.Random(seed)
        self.start_block = start_block

        self.results_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"pairwise_{parameter}_{pair_version}_{participant}_{stamp}"
        self.out_path = self.results_dir / f"{prefix}.csv"
        self.design_path = self.results_dir / f"{prefix}_design.csv"

        self.plan = self._make_plan()
        self._write_design()
        append_row_safely(self.out_path, RESULT_COLUMNS)

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
    def _make_plan(self):
        names = list(self.block_names(self.parameter))
        self.rng.shuffle(names)
        if self.start_block:
            first = next(n for n in names if n.lower() == self.start_block)
            names.remove(first)
            names.insert(0, first)

        plan = []
        for pos, name in enumerate(names, 1):
            mode, found = self.locate(name)
            if self.version_cfg["mode"] == "grid":
                test = [Item(i, "test", found[i]) for i in self.cfg["test_ids"]]
                foil = [Item(i, "foil", found[i]) for i in self.cfg["foil_ids"]]
                practice_trials = build_practice_trials(foil, self.rng) if USE_PRACTICE else []
                test_trials = build_test_trials(test, foil, self.rng)
            else:
                exp_ids_set = {sid for pair in self.cfg["pairs"] for sid in pair}
                items_by_id = {
                    sid: Item(sid, "experimental" if sid in exp_ids_set else "practice", found[sid])
                    for sid in found
                }
                practice_trials = (
                    build_fixed_practice_trials(self.cfg.get("practice_pairs", []), items_by_id)
                    if USE_PRACTICE else []
                )
                test_trials = build_explicit_test_trials(self.cfg["pairs"], items_by_id, self.rng)

            plan.append({
                "pos": pos, "name": name, "mode": mode,
                "practice": practice_trials,
                "trials": test_trials,
            })
        return plan

    def _write_design(self):
        append_row_safely(self.design_path, DESIGN_COLUMNS)
        for b in self.plan:
            for phase, trials in (("practice", b["practice"]), ("test", b["trials"])):
                for i, (first, second) in enumerate(trials, 1):
                    test_id, foil_id = test_foil_ids(first, second)
                    append_row_safely(self.design_path, [
                        self.participant, self.age, self.sex, self.level, self.parameter,
                        self.pair_version, b["pos"], b["name"], phase, i,
                        first.path.name, second.path.name,
                        first.id, second.id, test_id, foil_id])

    def show_instructions(self, instructions):
        pages = [instructions] if isinstance(instructions, str) else instructions
        for i, page in enumerate(pages):
            footer = "Pressez la barre d'espace pour continuer" if i < len(pages) - 1 else "Pressez la barre d'espace pour commencer"
            self.wait_space(f"{page}\n\n{footer}")

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
        out = Path(self.tmpdir.name) / f"clip_{len(self.sounds)}.wav"
        res = run_quiet([self.ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-i", str(path), "-vn",
                         "-ac", "2", "-ar", str(MIXER_FREQ), "-acodec", "pcm_s16le", str(out)],
                        capture_output=True, text=True, errors="replace", timeout=120)
        if res.returncode != 0:
            raise SystemExit(f"ffmpeg could not extract the audio of {path}:\n{res.stderr[-400:]}")
        return pygame.mixer.Sound(str(out))

    def _prepare_video(self, path):
        w, h, fps = probe_video(self.ffmpeg, path)
        scale = min(self.W / w, self.H / h)
        nw = max(2, int(w * scale) // 2 * 2)
        nh = max(2, int(h * scale) // 2 * 2)
        return {"w": nw, "h": nh, "fps": fps}

    def prepare(self):
        todo = []
        for block in self.plan:
            files = set()
            for trial in block["practice"] + block["trials"]:
                files.update(item.path for item in trial)
            todo += [(block["mode"], f) for f in sorted(files)]

        log = self.results_dir / "prepare_log.txt"
        log.write_text("", encoding="utf-8")
        for n, (mode, f) in enumerate(todo, 1):
            self.draw_text(f"Preparing stimuli… {n}/{len(todo)}")
            self.pump()
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"{n}/{len(todo)} {mode} {f}\n")
            if mode in ("audio", "both") and f not in self.sounds:
                self.sounds[f] = self._prepare_audio(f)
            if mode in ("video", "both") and f not in self.video_info:
                self.video_info[f] = self._prepare_video(f)

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
                proc = popen_quiet(
                    [self.ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(file), "-an",
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

    def ask_continue_practice(self, done):
        self.draw_text(f"{done} essais d'entraînement effectués.\n\n"
                       "Pour faire un autre essai d'entraînement,\nappuyez sur la barre d'espace.\n\n"
                       "Pour passer aux essais expérimentaux,\nappuyez sur Entrée.")
        pygame.event.clear()
        while True:
            for e in self.pump():
                if e.key == pygame.K_SPACE:
                    return True
                if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return False
            self.clock.tick(60)

    # ---------- trial / main flow ----------
    def run_trial(self, trial, phase, idx):
        first, second = trial
        mode = self.block["mode"]
        if phase == "test":
            self.trial_global += 1
        self.cur = {"phase": phase, "trial": idx, "first": first, "second": second,
                    "global": self.trial_global if phase == "test" else ""}
        self.trial_open = True

        self.draw_text("+")
        self.wait_ms(ITI_MS)
        self.draw_big("1")
        self.wait_ms(CUE_MS)
        self.play_clip(first.path, mode, "1")
        self.draw_text("+")
        self.wait_ms(ISI_MS)
        self.draw_big("2")
        self.wait_ms(CUE_MS)
        self.play_clip(second.path, mode, "2")
        response, rt = self.get_choice()

        self.save(response, "completed", rt)
        self.trial_open = False

    def run(self):
        try:
            self.prepare()
            self.show_instructions(self.cfg["instructions"])
            n_blocks = len(self.plan)
            for bi, block in enumerate(self.plan):
                self.block = block
                if block["practice"]:
                    self.wait_space(f"Bloc {bi + 1} sur {n_blocks}.\n\n"
                                    "Commencez par un entraînement pour vous familiariser avec la tâche. "
                                    "Il ne fait pas partie du test.\n\n"
                                    f"Après au moins {PRACTICE_MIN} essais, vous pourrez passer aux essais "
                                    "expérimentaux.\n\n"
                                    "Appuyez sur la barre d'espace pour commencer l'entraînement.")
                    n_practice = len(block["practice"])
                    for i, trial in enumerate(block["practice"], 1):
                        self.run_trial(trial, "practice", i)
                        if PRACTICE_MIN <= i < n_practice and not self.ask_continue_practice(i):
                            break
                    self.wait_space("L'entraînement est terminé.\n\nLa série de tests commence maintenant.\n\n"
                                    "Appuyez sur la barre d'espace pour continuer.")
                else:
                    self.wait_space(f"Bloc {bi + 1} sur {n_blocks}.\n\n"
                                    "Appuyez sur la barre d'espace pour commencer.")

                for i, trial in enumerate(block["trials"], 1):
                    self.run_trial(trial, "test", i)

                if bi < n_blocks - 1:
                    self.wait_space(f"Le bloc {bi + 1} sur {n_blocks} est terminé.\n\n"
                                    "Faites une petite pause. Appuyez sur la barre d'espace pour continuer.")
            self.wait_space("L'expérience est terminée. Merci ! Appuyez sur la barre d'espace pour quitter.")
        except Abort:
            pass
        finally:
            self.shutdown()

    # ---------- saving / shutdown ----------
    def save(self, response, status, rt=None):
        c = self.cur
        first, second = c["first"], c["second"]
        chosen = None
        if response != "":
            chosen = first if response == 1 else second
        test_id, foil_id = test_foil_ids(first, second)
        append_row_safely(self.out_path, [
            self.participant, self.age, self.sex, self.level, self.parameter,
            self.pair_version, self.block["name"], c["phase"], first.path.name, second.path.name,
            pair_label(first, second), response, chosen.path.name if chosen else "", status,
            self.block["pos"], c["trial"], c["global"],
            "" if rt is None else f"{rt:.3f}",
            datetime.now().isoformat(timespec="seconds"),
            first.id, second.id, test_id, foil_id,
            chosen.id if chosen else "", chosen.role if chosen else ""])

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


def main(experiment_cls):
    ap = argparse.ArgumentParser()
    ap.add_argument("--participant", required=True)
    ap.add_argument("--age", required=True)
    ap.add_argument("--sex", required=True)
    ap.add_argument("--level", required=True)
    ap.add_argument("--parameter", required=True, type=str.lower, choices=sorted(_PARAMETER_TEXTS),
                    help="synch = temporal alignment (knee flexion / racket head); "
                         "speed = racket-head speed at impact")
    ap.add_argument("--pair-version", type=str.lower, default=DEFAULT_PAIR_VERSION,
                    choices=sorted(PAIR_VERSIONS),
                    help=f"pair set version (default: {DEFAULT_PAIR_VERSION})")
    ap.add_argument("--start-block", type=str.lower, default=None,
                    help="block to run first (the others stay in random order)")
    ap.add_argument("--seed", type=int, default=None, help="optional, for reproducible order")
    args = ap.parse_args()

    valid = [n.lower() for n in experiment_cls.block_names(args.parameter)]
    if args.start_block and args.start_block not in valid:
        ap.error(f"--start-block for '{args.parameter}' must be one of: {', '.join(valid)}")

    experiment_cls(args.participant, args.age, args.sex, args.level,
                   args.parameter, args.seed, args.start_block,
                   pair_version=args.pair_version).run()