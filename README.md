# MixSon: perceptual experiments (MOS and pairwise comparisons)

Perceptual experiments for audio-visual synchronization with sonification:

- `mos_modality.py`: audio-only, video-only and audiovisual clips (three blocks, one per modality).
- `mos_strategy.py`: audiovisual clips only; one block per sonification strategy.

Both scripts require the `--parameter` flag, which selects the task and the media:

  - `synch`: Mean Opinion Score (1-5) rating
  - `speed`: pairwise comparison ("Which service was faster at impact?")

Everything runs in a single fullscreen window, and every response is written to
disk immediately, so data are safe even if a session is interrupted.

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Stimuli](#stimuli)
- [Running an experiment](#running-an-experiment)
- [Output](#output)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12 | |
| pygame | 2.6.1 | installed via conda or pip |
| ffmpeg + ffprobe | | must be on your PATH |

All other imports (`argparse`, `csv`, `queue`, `re`, `subprocess`, `threading`, `wave`, etc.)
are part of Python's standard library and need no installation.

Developed and tested on **macOS 12**. Windows and Linux are untested: run a trial
session before collecting real data.

## Installation

This installs Python, ffmpeg, ffprobe and pygame in one step.

1. Install **Miniconda** (from the Anaconda/Miniconda website) if you don't have conda.
2. Get the code:
   ```bash
   git clone https://github.com/OBrienBenjamin/MixSon_Experiment.git
   cd MixSon_Experiment
   ```

3. Create and activate the environment:
   ```bash
   conda env create -f environment.yaml
   conda activate your_env
   ```

### Check the installation

```bash
python check_setup.py
```

It verifies Python, pygame, ffmpeg, ffprobe and the media folder, and prints `[OK]`
or `[FAIL]` with a hint for each. You can also check manually:

```bash
python --version
ffmpeg -version
python -c "import pygame; print(pygame.version.ver)"
```

## Stimuli

The stimulus files are not stored in this repository (about 1.2 GB) and will be provided by the author to engineer. The `media.zip` file should be unzipped and included in the main folder `MixSon_Experiment`.

After unzipping, the `media/` folder must have this structure:

```
media/
├── Audio/    .wav   (mos_modality.py only)
├── Video/    .mov   (mos_modality.py only)
└── AV/       .mp4   (mos_modality.py and mos_strategy.py)
```

All files are selected **by name**. `<prefix>` is `Speed` (for `--parameter speed`) or
`Synch` (for `--parameter synch`), and `<n>` is an integer. Capitalization does not matter.

### `mos_modality.py`

| Folder | File name | Speed example | Synch example |
|---|---|---|---|
| `Audio/` | `<prefix>_<n>_<suffix>.wav` | `Speed_37_Step.wav` | `Synch_75_Event.wav` |
| `AV/` | `<prefix>_<n>_<suffix>.mp4` | `Speed_37_Step.mp4` | `Synch_75_Event.mp4` |
| `Video/` | `<prefix>_<n>.mov` | `Speed_37.mov` | `Synch_75.mov` |

The suffix is `Step` for `speed` and `Event` for `synch`.

### `mos_strategy.py`

Only `AV/` is used, and each block (strategy) reads the files carrying its own suffix:

| `--parameter` | Blocks (random order) | Files read from `AV/` |
|---|---|---|
| `speed` | Step, OSC, BPF | `Speed_<n>_Step.mp4`, `Speed_<n>_OSC.mp4`, `Speed_<n>_BPF.mp4` |
| `synch` | Event, Static, Centroid | `Synch_<n>_Event.mp4`, `Synch_<n>_Static.mp4`, `Synch_<n>_Centroid.mp4` |

### Practice and test clips

Practice clips are identified by their number; all other matching files are test clips.

| `--parameter` | Practice numbers | Test clips per block |
|---|---|---|
| `speed` | 32, 34, 50, 53 | 6 |
| `synch` | 75, 400 | 8 |

Practice clips use the same name pattern as the block's test clips (for example
`Speed_32_OSC.mp4` is the practice clip of the OSC block, and `Speed_32.mov` that of the
Video block). Files that don't match the pattern of the block (for example other strategies
in the same folder) are ignored.

Supported formats: `.wav` (Audio), `.mov` (Video), `.mp4` (AV). Every AV clip needs an audio track.
If a block does not find the expected number of clips, the script stops and lists the files it found.

## Running an experiment

Activate the environment first (`conda activate your_env`), then:

```bash
# Modality experiment: choose the task with --parameter
python mos_modality.py --participant P01 --parameter synch    # MOS rating
python mos_modality.py --participant P01 --parameter speed    # pairwise comparison

# Strategy experiment
python mos_strategy.py --participant P01 --parameter synch    # MOS rating
python mos_strategy.py --participant P01 --parameter speed    # pairwise comparison
```

Options:

| Flag | Meaning |
|---|---|
| `--participant ID` | required: participant identifier, used in the output file names |
| `--parameter {synch,speed}` | required: which task to run (see below) |
| `--start-block NAME` | optional: run this block first; the other blocks stay in random order. `mos_modality.py`: `audio`, `video`, `audiovisual`. `mos_strategy.py`: `step`, `osc`, `bpf` (speed) or `event`, `static`, `centroid` (synch) |
| `--seed N` | optional: makes block and trial order reproducible |

Example: `python mos_strategy.py --participant P02 --parameter speed --start-block osc`

### The two tasks (both scripts)

| | `--parameter synch` | `--parameter speed` |
|---|---|---|
| Task | MOS rating | pairwise comparison |
| File prefix | `Synch_` | `Speed_` |
| Test clips per block | 8 | 6 |
| Trials per block | 8 clips x 1 repetition = 8 | 15 pairs x 2 orders (AB and BA) = 30 |
| Presentation | one clip per trial | two clips one after the other (1 s pause) |
| Response | rate the clip with keys **1-5** (1 = bad, 5 = excellent) | key **1** = first clip, **2** = second clip |
| Practice | 2 trials (clips 75 and 400) | 2 trials (32 vs 50 and 34 vs 53, each in a random order AB or BA) |

The difference between the two scripts is the media used for the blocks (3 blocks each,
presented in random order for every participant):

| | Blocks | Media |
|---|---|---|
| `mos_modality.py` | Audio-only, Video-only, Audiovisual | `Audio/`, `Video/`, `AV/` |
| `mos_strategy.py` | `speed`: Step, OSC, BPF<br>`synch`: Event, Static, Centroid | `AV/` (all blocks audiovisual) |

A short practice is run before each block. The practice trials are logged with
`phase = practice` and are not part of the test.

In the `speed` task, every pair of clips is shown in both orders, and the two orders of the same
pair never appear back to back. In the `synch` task, all clips in a block are shuffled and a clip
only repeats after every clip in the block has been shown.

### During the session

- **SPACE**: start the experiment / continue after a break
- **1-5** (`synch`) or **1 / 2** (`speed`): respond after the clip(s) finish
- **ESC**: quit at any time; the interrupted trial is logged as `aborted`

**Before each session:** close other applications, set the system volume to the level
you want, use the same headphones/speakers for all participants, and on macOS set the Dock
to auto-hide.

## Output

Written to `Responses/Modality/` for `mos_modality.py` and `Responses/Strategy/` for `mos_strategy.py` (not tracked by git).

| Script | Task | File |
|---|---|---|
| `mos_modality.py` | synch | `mos_synch_<participant>_<timestamp>.csv` |
| `mos_modality.py` | speed | `pairwise_speed_<participant>_<timestamp>.csv` |
| `mos_strategy.py` | synch | `strategy_mos_synch_<participant>_<timestamp>.csv` |
| `mos_strategy.py` | speed | `strategy_pairwise_speed_<participant>_<timestamp>.csv` |
| both | both | `<same name>_design.csv`: the planned trial order for that session |

Columns, `--parameter synch`:
`participant, parameter, block, phase, stimulus, repetition, response, status,
block_order_pos, trial_in_block, trial_global, rt_after_playback_s, timestamp`

Columns, `--parameter speed`:
`participant, parameter, block, phase, first, second, pair, response, chosen, status,
block_order_pos, trial_in_block, trial_global, rt_after_playback_s, timestamp`

- `block` is the modality (Audio, Video, Audiovisual) in `mos_modality.py` and the strategy
  (Step, OSC, BPF, Event, Static, Centroid) in `mos_strategy.py`.
- `response` is the rating (1-5) in `synch`, or 1 or 2 (first or second) in `speed`; `chosen` is the
  file that was picked as faster.
- `phase` is `practice` or `test`; `status` is `completed` or `aborted`.
- For analysis, keep rows where `phase == test` and `status == completed`.

Each response is flushed to disk immediately, so data survive crashes.

## Configuration

Constants at the top of `mos_modality.py` and `mos_strategy.py`:

| Setting | Purpose |
|---|---|
| `PARAMETERS` | per-task settings: file prefix, suffix (modality) or strategies (strategy), test clips per block, repetitions (`synch`), practice numbers (`train_ids`, `practice_pairs`), question and instruction text |
| `BLOCKS` (`mos_modality.py`) | blocks with their folder, mode and file extension |
| `USE_PRACTICE` | turn the practice trials before each block on or off |
| `ALLOW_MISSING_AUDIO` | `True` plays clips without an audio track silently (for testing only) |
| `ITI_MS`, `CUE_MS`, `ISI_MS` | fixation, "1"/"2" cue and pause between the two clips (`speed`) |
| `SCALE_LABELS` | labels of the 1-5 rating scale (`synch`) |
| `CANVAS` | internal render size (lower it if video is choppy) |
| `MIXER_FREQ` | audio sample rate; set to your files' rate (44100 or 48000) |

## Troubleshooting

- **`ffmpeg/ffprobe not found`**: activate the conda env, or install ffmpeg.
- **`expected N test files named ..., found M`**: a block does not contain the expected number of
  clips. The message lists the files that were counted; check the file names against the
  naming rules (see Stimuli).
- **`missing practice file(s): ...`**: add the listed practice clips, or set `USE_PRACTICE = False`.
- **`No audio track found in ...`**: re-export that clip with its audio track (needed for the AV blocks).
- **`Folder not found`**: the `media/` folder is missing or not in the main `MixSon_Experiment` folder (see Stimuli).
- **`error: argument --parameter ... invalid choice` / `--start-block ... must be one of`**: use
  `--parameter synch` or `speed`, and a block name listed in the options table.
- **Choppy video**: re-encode clips to H.264, 720p or 1080p, 25-30 fps, or lower `CANVAS`.
- **Dock/menu bar visible (macOS)**: set the Dock to auto-hide during sessions.

## Stimuli

Available on request
