# MixSon: audio-visual MOS rating experiment

Runs a Mean Opinion Score (1–5) experiment with three blocks of 8 clips each
(audio-only, video-only, audiovisual). Block order is randomized per participant.
Within a block the 8 clips are shuffled and the full set is repeated 5 times
(a clip repeats only after all 8 have been shown). Each clip plays automatically,
then the participant rates it with keys 1–5. Everything runs in one fullscreen window.

## Requirements

- Python 3.12
- ffmpeg and ffprobe (on PATH)
- pygame ≥ 2.5

Developed and tested on macOS 12 with Python 3.12, pygame <VERSION>, ffmpeg <VERSION>.
Other platforms are untested.

## Install

```bash
git clone https://github.com/<user>/<repo>.git
cd <repo>

# recommended: conda
conda env create -f environment.yml
conda activate mixson
```

Without conda: install Python 3.12 and ffmpeg yourself, then
`pip install -r requirements.txt`.

Check it worked:

```bash
python --version        # 3.12.x
ffmpeg -version
python -c "import pygame; print(pygame.version.ver)"
```

## Stimuli

The stimulus files are not stored in this repository (about 1.2 GB).

1. Download `mixson_stimuli.zip` from: <PASTE GOOGLE DRIVE LINK>
2. Unzip it in the repository root so the folder structure is:

```
media/MOS/Modality/{AV,Audio,Video}/
media/MOS/Strategy/{EVENT,FM,STATIC}/
```

Check with: `ls media/MOS`


## Run

```bash
python scripts/manip.py --participant P01
```

Options: `--seed 123` (reproducible order).
Press SPACE to start/continue, keys 1–5 to rate, ESC to quit
(the interrupted trial is logged as `aborted`).

## Output

Written to `results/` (not tracked by git):

- `results_<participant>_<timestamp>.csv`: one row per trial
  (participant, block, stimulus, repetition, response, status, block position,
  trial numbers, reaction time after playback, timestamp)
- `results_<participant>_<timestamp>_design.csv`: the planned trial order

Each response is flushed to disk immediately, so data survive crashes.

## Configuration

Edit the constants at the top of `scripts/manip.py`: number of repetitions, question
text and scale labels, render size (`CANVAS`), audio sample rate (`MIXER_FREQ`).

## Troubleshooting

- **`ffmpeg/ffprobe not found`**: activate the conda env, or install ffmpeg.
- **Choppy video**: re-encode clips to H.264, 720p or 1080p, 25–30 fps, or lower `CANVAS`.
- **Dock/menu bar visible (macOS)**: set the Dock to auto-hide during sessions.

## Licence / stimuli

<code licence> · <stimuli licence or note on permissions>


