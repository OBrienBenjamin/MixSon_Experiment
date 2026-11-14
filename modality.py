"""Modality experiment: audio-only, video-only and audiovisual blocks.

    python modality.py --participant P01 --age 25 --sex F --level expert --parameter speed

Media: media/<Audio|Video|AV>/<speed|synch>_<n>[_suffix].<ext>   (see README)
"""
from experiment_core import BaseExperiment, HERE, MEDIA_ROOT, find_media, main

BLOCKS = {                       # block name -> (folder, mode, extension, file name has the _<suffix>?)
    "Audio":       ("Audio", "audio", ".wav", True),
    "Video":       ("Video", "video", ".mp4", False),
    "Audiovisual": ("AV",    "both",  ".mp4", True),
}

# Audio and AV file names: <parameter>_<n><suffix>.<ext>   (Video files have no suffix)
SUFFIX = {"synch": "_Event", "speed": "_Step"}


class Experiment(BaseExperiment):
    results_dir = HERE / "Responses" / "Modality"

    @classmethod
    def block_names(cls, parameter):
        return list(BLOCKS)

    def locate(self, name):
        folder, mode, ext, uses_suffix = BLOCKS[name]
        suffix = SUFFIX[self.parameter] if uses_suffix else ""
        return mode, find_media(MEDIA_ROOT / folder, ext, self.cfg["prefix"], suffix, self.all_ids)


if __name__ == "__main__":
    main(Experiment)
