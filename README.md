# MixSon: MOS perceptual experiment

Two Mean Opinion Score (1-5) rating experiments for audio-visual synchronization
with sonification:

- `mos_modality.py`: audio-only, video-only and audiovisual clips
- `mos_strategy.py`: <short description, e.g. EVENT / FM / STATIC sonification strategies>

Each clip plays automatically, then the participant rates it with keys 1-5.
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
| pygame | <PINNED VERSION, e.g. 2.6.1> | installed via conda or pip |
| ffmpeg + ffprobe | <VERSION> | must be on your PATH |

All other imports (`argparse`, `csv`, `queue`, `subprocess`, `threading`, `wave`, etc.)
are part of Python's standard library and need no installation.

Developed and tested on **macOS 12**. Windows and Linux are untested: run a trial
session before collecting real data.

## Installation

### Option 1 (recommended): conda

This installs Python, ffmpeg, ffprobe and pygame in one step.

1. Install **Miniconda** (from the Anaconda/Miniconda website) if you don't have conda.
2. Get the code:
   ```bash
   git clone https://github.com/<user>/<repo>.git
   cd <repo>
   ```
   (or use "Code -> Download ZIP" on GitHub and open a terminal in the unzipped folder)
3. Create and activate the environment:
   ```bash
   conda env create -f environment.yaml
   conda activate mixson
   ```

### Option 2: setup script

From the repo folder:

```bash
bash setup.sh        # macOS / Linux
setup.bat            # Windows
```

These use conda if it is available, otherwise they create a `.venv` and install
`requirements.txt`. In the venv case **ffmpeg must be installed separately**
(see below).

### Option 3: pip only

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Then install ffmpeg yourself and make sure both `ffmpeg` and `ffprobe` run from a terminal
(download from ffmpeg.org, or use a package manager).

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

The stimulus files are not stored in this repository (about 1.2 GB) and will be provided by the author to engineer. The 'media.zip' file should be unziped and included in the main folder 'MixSon_Experiment'

## Run

Activate the environment first (`conda activate mixson`, or activate the `.venv`), then:

```bash
python mos_modality.py --participant P01
python mos_strategy.py --participant P01
```

Options:

| Option | Meaning |
|---|---|
| `--participant ID` | participant identifier (required), used in the output file names |
| `--seed N` | optional: makes block and trial order reproducible |

During the session:

- **SPACE**: start the experiment / continue after a break
- **1-5**: rate the clip (shown after each clip finishes)
- **ESC**: quit at any time; the interrupted trial is logged as `aborted`

Block order is randomized per participant. Within a block, all clips are shuffled and the full
set is repeated <N_REPS> times; a clip only repeats after every clip in the block has been shown.

**Before each session:** close other applications, set the system volume to the level
you want, use the same headphones/speakers for all participants, and on macOS set the Dock
to auto-hide.

## Output

Written to `Responses/MOS/` (not tracked by git):

- `mos_<experiment_type>_<participant>_<timestamp>.csv`: one row per trial
  (participant, block, stimulus, repetition, response, status, block position,
  trial numbers, reaction time after playback, timestamp)
- `mos_<experiment_type>_<participant>_<timestamp>_design.csv`: the planned trial order

Each response is flushed to disk immediately, so data survive crashes.

## Troubleshooting

- **`ffmpeg/ffprobe not found`**: activate the conda env, or install ffmpeg.
- **Choppy video**: re-encode clips to H.264, 720p or 1080p, 25–30 fps, or lower `CANVAS`.
- **Dock/menu bar visible (macOS)**: set the Dock to auto-hide during sessions.

## Licence / stimuli

Coming soon . . . 


