# MixSon: perceptual experiments (pairwise comparisons)

Perceptual experiments on tennis services. In every trial the participant perceives two
services one after the other and decides which of the two is the better one on a given criterion.
The criterion is selected with the `--parameter` flag:

| `--parameter` | Question asked (shown in French) |
|---|---|
| `synch` | Which service has the better synchronisation between maximal knee flexion and the maximal vertical position of the racket head? |
| `speed` | Which service has the higher racket-head speed at impact? |

Two experiments use the same procedure with different media:

- `modality.py`: audio-only, video-only and audiovisual clips (three blocks, one per modality).
- `strategy.py`: audiovisual clips only; one block per sonification strategy.

Both scripts share their code (`experiment_core.py`). Everything runs in a single fullscreen window
with on-screen text in French, and every response is written to disk immediately, so data are safe
even if a session is interrupted.

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Experimental design](#experimental-design)
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
| ffmpeg | | bundled by the `imageio-ffmpeg` package; an ffmpeg on your PATH also works (ffprobe is not needed) |

All other imports (`argparse`, `csv`, `queue`, `re`, `subprocess`, `threading`, `wave`, etc.)
are part of Python's standard library and need no installation.

Developed and tested on **macOS 12**. Windows and Linux are untested: run a trial
session before collecting real data.

## Installation

This installs Python, ffmpeg and pygame in one step.

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

It verifies Python, pygame, ffmpeg and the media folder, and prints `[OK]`
or `[FAIL]` with a hint for each. You can also check manually:

```bash
python --version
python -c "import pygame; print(pygame.version.ver)"
```

## Experimental design

Each stimulus is identified by a number `<n>` in its file name. For each parameter the numbers are
split into **test** items and **foil** items:

| `--parameter` | Test items | Foil items |
|---|---|---|
| `synch` | 50, 100, 150, 240, 350 | 6, 75, 200, 300, 400 |
| `speed` | 34, 39, 41, 45, 50 | 32, 37, 43, 47, 53 |

**Experimental trials (per block)**

- Every test item is compared with every foil item: 5 x 5 = **25 pairs**.
- Every pair is shown in both orders (AB and BA): **50 trials per block**, in random order.
  The two orders of the same pair never appear back to back.
- Each experiment has 3 blocks (modalities for `modality.py`, strategies for `strategy.py`),
  presented in random order for every participant: 150 experimental trials per participant and parameter.

**A trial**

1. fixation cross, then the cue "1", then the first clip;
2. a 1 s pause, then the cue "2", then the second clip;
3. the question appears. The participant answers **1** (first clip) or **2** (second clip).

**Practice (before each block)**

- Practice pairs are made **only from foil items**: no test item is ever shown during practice.
- All foil pairs are available in both orders (10 pairs x 2 = 20 trials). The first 10 trials show every pair
  once (random order AB or BA); the next 10 show the same pairs reversed.
- After at least **5** practice trials (`PRACTICE_MIN`) the participant is asked, after each trial,
  to press **SPACE** for another practice trial or **ENTER** to go to the experimental trials.
  After all 20 trials the experimental trials start automatically.
- Practice trials are logged with `phase = practice` and are not part of the test.

## Stimuli

The stimulus files are not stored in this repository (about 1.2 GB) and are available on request. Unzip
`media.zip` into the main folder `MixSon_Experiment`.

Files are selected **by name**: `<prefix>_<n>[_<suffix>].<ext>`, where `<prefix>` is `Speed` or `Synch`
(for `--parameter speed` or `synch`), `<n>` is one of the test or foil numbers above, and capitalization does not
matter. Every number of the chosen parameter (test and foil, 10 per block) must exist; files with other numbers or
other suffixes in the same folder are ignored.

### `modality.py`

| Folder | File name | Speed example | Synch example |
|---|---|---|---|
| `media/Audio/` | `<prefix>_<n>_<suffix>.wav` | `Speed_34_Step.wav` | `Synch_50_Event.wav` |
| `media/AV/` | `<prefix>_<n>_<suffix>.mp4` | `Speed_34_Step.mp4` | `Synch_50_Event.mp4` |
| `media/Video/` | `<prefix>_<n>.mp4` | `Speed_34.mp4` | `Synch_50.mp4` |

The suffix is `Step` for `speed` and `Event` for `synch`.

### `strategy.py`

Only `media/AV/` is used (`.mp4`). Each block (strategy) reads the files carrying its own suffix:

| `--parameter` | Blocks (random order) | Files read from `media/AV/` |
|---|---|---|
| `speed` | Step, OSC, BPF | `Speed_<n>_Step.mp4`, `Speed_<n>_OSC.mp4`, `Speed_<n>_BPF.mp4` |
| `synch` | Event, Static, Centroid | `Synch_<n>_Event.mp4`, `Synch_<n>_Static.mp4`, `Synch_<n>_Centroid.mp4` |

Every AV clip needs an audio track.

## Running an experiment

Activate the environment first (`conda activate your_env`), then:

```bash
# Modality experiment
python modality.py --participant P01 --age 25 --sex F --level expert --parameter synch
python modality.py --participant P01 --age 25 --sex F --level expert --parameter speed

# Strategy experiment
python strategy.py --participant P01 --age 25 --sex F --level expert --parameter synch
python strategy.py --participant P01 --age 25 --sex F --level expert --parameter speed
```

Options:

| Flag | Meaning |
|---|---|
| `--participant ID` | required: participant identifier, used in the output file names |
| `--age`, `--sex`, `--level` | required: participant details, saved in every row of the results |
| `--parameter {synch,speed}` | required: which question to ask (see the table at the top) |
| `--start-block NAME` | optional: run this block first; the other blocks stay in random order. `modality.py`: `audio`, `video`, `audiovisual`. `strategy.py`: `step`, `osc`, `bpf` (speed) or `event`, `static`, `centroid` (synch) |
| `--seed N` | optional: makes block and trial order reproducible |

Example: `python strategy.py --participant P02 --age 31 --sex M --level novice --parameter speed --start-block osc`

### During the session

- **SPACE**: continue (instructions, breaks, start of a block) / another practice trial
- **1** or **2**: answer after the second clip
- **ENTER**: after at least 5 practice trials, go on to the experimental trials
- **ESC**: quit at any time; the interrupted trial is logged as `aborted`

**Before each session:** close other applications, set the system volume to the level
you want, use the same headphones/speakers for all participants, and on macOS set the Dock
to auto-hide.

## Output

Written to `Responses/Modality/` for `modality.py` and `Responses/Strategy/` for `strategy.py` (not tracked by git).

| File | Content |
|---|---|
| `pairwise_<parameter>_<participant>_<timestamp>.csv` | one row per trial |
| `pairwise_<parameter>_<participant>_<timestamp>_design.csv` | the planned trial order for that session (including all 20 practice trials per block, of which only the ones actually shown are in the results) |

Columns of the results file:

| Column | Meaning |
|---|---|
| `participant`, `age`, `sex`, `level` | participant details |
| `parameter` | `synch` or `speed` |
| `block` | modality (Audio, Video, Audiovisual) in `modality.py`; strategy (Step, OSC, BPF, Event, Static, Centroid) in `strategy.py` |
| `phase` | `practice` or `test` |
| `first`, `second`, `pair` | file names of the first and second clip, and the pair (independent of the order) |
| `response` | 1 = first clip chosen, 2 = second clip chosen (empty if aborted) |
| `chosen` | file name of the chosen clip |
| `status` | `completed` or `aborted` |
| `block_order_pos`, `trial_in_block`, `trial_global` | position of the block, trial number in the block, and trial number over the whole session (test trials only) |
| `rt_after_playback_s` | reaction time, measured from the moment the question appears |
| `timestamp` | time of the response |
| `first_id`, `second_id` | stimulus numbers of the first and second clip |
| `test_id`, `foil_id` | stimulus numbers of the test and the foil item of the pair (empty in practice, where both are foils) |
| `chosen_id`, `chosen_role` | number of the chosen clip, and whether it was the `test` or the `foil` item |

For analysis, keep rows where `phase == test` and `status == completed`. For each block, test item and foil item,
the proportion of trials with `chosen_role == test` is the usual outcome (two trials per pair, one in each order).

Each response is flushed to disk immediately, so data survive crashes.

## Configuration

Constants at the top of `experiment_core.py`:

| Setting | Purpose |
|---|---|
| `PARAMETERS` | per parameter: file prefix, `test_ids`, `foil_ids`, question and instruction texts |
| `USE_PRACTICE`, `PRACTICE_MIN` | practice before each block; number of practice trials before the participant may skip |
| `ALLOW_MISSING_AUDIO` | `True` plays clips without an audio track silently (for testing only) |
| `ITI_MS`, `CUE_MS`, `ISI_MS` | fixation, "1"/"2" cue and pause between the two clips |
| `CHOICE_LABELS` | labels of the two answers |
| `CANVAS` | internal render size (lower it if video is choppy) |
| `MIXER_FREQ` | audio sample rate; set to your files' rate (44100 or 48000) |

`modality.py`: `BLOCKS` (folders and extensions of the three modalities) and `SUFFIX` (file name suffix
of each parameter). `strategy.py`: `STRATEGIES` (blocks of each parameter).

## Troubleshooting

- **`ffmpeg not found`**: activate the conda env, or run `pip install imageio-ffmpeg`.
- **`missing file(s): ...`**: the named files are not in the folder. Check the file names against the naming rules
  (see Stimuli).
- **`two files match ...`**: two files in a folder have the same number and suffix (differing only in capitalization);
  keep one.
- **`Folder not found`**: the `media/` folder (or one of its subfolders) is missing or not in the main
  `MixSon_Experiment` folder (see Stimuli).
- **`No audio track found in ...`**: re-export that clip with its audio track (needed for the audio and AV blocks).
- **`error: the following arguments are required: ...`**: `--participant`, `--age`, `--sex`, `--level`
  and `--parameter` must all be given.
- **`--parameter ... invalid choice` / `--start-block ... must be one of`**: use `--parameter synch` or `speed`,
  and a block name listed in the options table.
- **Choppy video**: re-encode clips to H.264, 720p or 1080p, 25-30 fps, or lower `CANVAS`.
- **Dock/menu bar visible (macOS)**: set the Dock to auto-hide during sessions.

## Licence / stimuli

Licence: coming soon. Stimuli: available on request.
