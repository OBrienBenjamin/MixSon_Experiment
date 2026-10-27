# MixSon: perceptual experiments (MOS and pairwise comparisons)

Perceptual experiments for audio-visual synchronization with sonification:

- `mos_modality.py`: audio-only, video-only and audiovisual clips. 
- `mos_strategy.py`: sonification strategy {3-different strategies}

Both scripts require setting the `--parameter` flag, which selects the task / media :
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
| ffmpeg + ffprobe | |

All other imports (`argparse`, `csv`, `queue`, `subprocess`, `threading`, `wave`, etc.)
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
├── Modality/
│   ├── Synch/                     (used with --parameter synch)
│   │   ├── Audio/                 8 clips
│   │   ├── Video/                 8 clips
│   │   ├── AV/                    8 clips
│   │   └── Train/{Audio,Video,AV}/    2 practice clips each
│   └── Speed/                     (used with --parameter speed)
│       ├── Audio/                 6 clips
│       ├── Video/                 6 clips
│       ├── AV/                    6 clips
│       └── Train/{Audio,Video,AV}/    2 practice clips each
└── Strategy/                      (used by mos_strategy.py)
```

Supported formats: `.mp4`, `.wav`. Each folder must contain exactly the expected
number of files, otherwise the script stops with a message naming the folder.

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

| Option | Meaning |
|---|---|
| `--participant ID` | participant identifier (required), used in the output file names |
| `--parameter {synch,speed}` |
| `--seed N` | optional: makes block and trial order reproducible |

### Both tasks of `mos_modality.py` and `mos_strategy.py`

| | `--parameter synch` | `--parameter speed` |
|---|---|---|
| Task | MOS rating | pairwise comparison |
| Stimuli folder | `media/{--parameter}/Synch/` | `media/{--parameter}/Speed/` |
| Clips per block | 8 | 6 |
| Trials per block | 8 clips x 1 repetition = 8 | 15 pairs x 2 orders (AB and BA) = 30 |
| Presentation | one clip per trial | two clips one after the other (1 s pause) |
| Response | rate the clip with keys **1-5** (1 = bad, 5 = excellent) | key **1** = first clip, **2** = second clip |

The difference between the two scripts centers on the media used:

`mos_modality.py` : 
| Blocks | Audio-only, Video-only, Audiovisual (random order) | Audio-only, Video-only, Audiovisual (random order) |

`mos_strategy.py` : 
| Blocks | 3-Different Sonification strategies (random order) | Audiovisual |

A short practice (2 trials) is run before each block, using the files in the matching
`Train/` folder. The practice trials are logged with `phase = practice` and are not part of
the test.

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

| File | Content |
|---|---|
| `mos_synch_<participant>_<timestamp>.csv` | one row per trial (MOS) |
| `pairwise_speed_<participant>_<timestamp>.csv` | one row per trial (pairwise) |
| `<same name>_design.csv` | the planned trial order for that session |

Columns, `--parameter synch`:
`participant, parameter, block, phase, stimulus, repetition, response, status,
block_order_pos, trial_in_block, trial_global, rt_after_playback_s, timestamp`

Columns, `--parameter speed`:
`participant, parameter, block, phase, first, second, pair, response, chosen, status,
block_order_pos, trial_in_block, trial_global, rt_after_playback_s, timestamp`

- `response` is the rating (1-5) in `synch`, or 1/2 (first/second) in `speed`; `chosen` is the
  file that was picked as faster.
- `phase` is `practice` or `test`; `status` is `completed` or `aborted`.
- For analysis, keep rows where `phase == test` and `status == completed`.

Each response is flushed to disk immediately, so data survive crashes.

## Configuration

Constants at the top of `mos_modality.py` and `mos_strategy.py`:

| Setting | Purpose |
|---|---|
| `PARAMETERS` | per-task settings: stimuli folder, clips per block, repetitions (`synch`), question and instruction text |
| `USE_PRACTICE`, `N_PRACTICE`, `TRAIN_DIRNAME` | practice trials before each block |
| `ITI_MS`, `CUE_MS`, `ISI_MS` | fixation, "1"/"2" cue and pause between the two clips (`speed`) |
| `SCALE_LABELS` | labels of the 1-5 rating scale (`synch`) |
| `CANVAS` | internal render size (lower it if video is choppy) |
| `MIXER_FREQ` | audio sample rate; set to your files' rate (44100 or 48000) |

## Troubleshooting

- **`ffmpeg/ffprobe not found`**: activate the conda env, or install ffmpeg.
- **`Folder not found: .../Train/...`**: the practice folders are missing. Add them
  (see Stimuli) or set `USE_PRACTICE = False`.
- **`expected N files, found M`**: each stimulus folder must contain exactly the expected number of clips.
- **`error: argument --parameter ... invalid choice`**: use `--parameter synch` or `--parameter speed`.
- **Choppy video**: re-encode clips to H.264, 720p or 1080p, 25–30 fps, or lower `CANVAS`.
- **Dock/menu bar visible (macOS)**: set the Dock to auto-hide during sessions.

## Licence / stimuli

Coming soon . . .
