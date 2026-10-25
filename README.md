# MixSon: audio-visual MOS rating experiment

Runs a Mean Opinion Score (1–5) experiment with three blocks of 8 clips. Two experiments are included which test the effects of modality
(audio-only, video-only, audiovisual) and sonification strategy (event, static, fm). Block order is randomized per participant.
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

The stimulus files are not stored in this repository (about 1.2 GB) and will be provided by the author to engineer. The 'media.zip' file should be unziped and included in the main folder 'MixSon_Experiment'

## Run

cd to the MixSon_Experiment directory. To run the 'Modality' Experiment type the following

```bash
python manip.py --participant P01
```

To run the 'Strategy' Experiment type the following

```bash
python manip.py --participant P01
```

Please replace P01 with the up-to-date participant identifier

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

<code licence> · <stimuli licence or note on permissions>


