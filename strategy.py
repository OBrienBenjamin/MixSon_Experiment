"""Strategy experiment: audiovisual clips only, one block per sonification strategy.

    python strategy.py --participant P01 --age 25 --sex F --level expert --parameter synch

Media: media/AV/<speed|synch>_<n>_<Strategy>.mp4   (see README)
"""
from experiment_core import BaseExperiment, HERE, MEDIA_ROOT, find_media, main

MEDIA_DIR = MEDIA_ROOT / "AV"
EXT = ".mp4"

# Blocks (= strategies) of each parameter; the file suffix is _<Strategy>
STRATEGIES = {
    "synch": ["Event", "Static", "Centroid"],
    "speed": ["Step", "OSC", "BPF"],
}


class Experiment(BaseExperiment):
    results_dir = HERE / "Responses" / "Strategy"

    @classmethod
    def block_names(cls, parameter):
        return STRATEGIES[parameter]

    def locate(self, name):
        # every block is audiovisual
        return "both", find_media(MEDIA_DIR, EXT, self.cfg["prefix"], f"_{name}", self.all_ids)


if __name__ == "__main__":
    main(Experiment)
