"""MixSon launcher: a small start screen so nobody needs a terminal."""
import argparse
import textwrap
import traceback
from datetime import datetime

import pygame

from appdir import app_dir
from experiment_core import DEFAULT_PAIR_VERSION, PAIR_VERSIONS
import modality
import strategy

EXPERIMENTS = [("Modality", modality), ("Strategy", strategy)]
PARAMETERS = [("Synch", "synch", "pairwise comparison"),
              ("Speed", "speed", "pairwise comparison")]
PAIR_VERSION_CHOICES = sorted(PAIR_VERSIONS.keys())

BG, FG, DIM, ACCENT, ERR = (20, 20, 20), (235, 235, 235), (140, 140, 140), (90, 170, 255), (255, 130, 130)


def log_error(text):
    log_dir = app_dir() / "Responses"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "error_log.txt"
    with open(path, "a") as f:
        f.write(f"\n--- {datetime.now().isoformat(timespec='seconds')} ---\n{text}\n")
    return path


def draw_menu(screen, fonts, st):
    big, mid, small = fonts
    W, _ = screen.get_size()
    screen.fill(BG)
    t = big.render("MixSon Experiments", True, FG)
    screen.blit(t, ((W - t.get_width()) // 2, 30))

    field_keys = ["id", "age", "sex", "level"]
    blink = "_" if (pygame.time.get_ticks() // 500) % 2 == 0 else ""
    exp_name = EXPERIMENTS[st["exp"]][0]
    par_name, _, _ = PARAMETERS[st["par"]]
    ver_name = PAIR_VERSION_CHOICES[st["ver"]]

    rows = [
        ("Participant ID", st["id"] + (blink if st["field"] == 0 else "")),
        ("Participant Age", st["age"] + (blink if st["field"] == 1 else "")),
        ("Participant Sex", st["sex"] + (blink if st["field"] == 2 else "")),
        ("Participant Level", st["level"] + (blink if st["field"] == 3 else "")),
        ("Experiment", f"<   {exp_name}   >"),
        ("Parameter", f"<   {par_name}   >"),
        ("Pair Version", f"<   {ver_name}   >"),
    ]
    y = 115
    for i, (label, value) in enumerate(rows):
        screen.blit(mid.render(label, True, DIM), (70, y))
        screen.blit(mid.render(value, True, ACCENT if st["field"] == i else FG), (330, y))
        y += 56

    hint = small.render("Tab / Up / Down: next field     Left / Right: change     "
                        "Enter: start     Esc: quit", True, DIM)
    screen.blit(hint, ((W - hint.get_width()) // 2, 68))

    if st["msg"]:
        lines = []
        for para in st["msg"].splitlines()[:8]:
            lines += textwrap.wrap(para, 80) or [""]
        y = 515
        for ln in lines[:6]:
            screen.blit(small.render(ln, True, ERR), (70, y))
            y += 24


def menu(screen, fonts, st):
    clock = pygame.time.Clock()
    field_keys = ["id", "age", "sex", "level"]
    NUM_FIELDS = 7  # ID, Age, Sex, Level, Experiment, Parameter, Pair Version

    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return None
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_ESCAPE:
                return None
            elif e.key in (pygame.K_TAB, pygame.K_DOWN):
                st["field"] = (st["field"] + 1) % NUM_FIELDS
            elif e.key == pygame.K_UP:
                st["field"] = (st["field"] - 1) % NUM_FIELDS
            elif e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                step = -1 if e.key == pygame.K_LEFT else 1
                if st["field"] == 4:      # Experiment
                    st["exp"] = (st["exp"] + step) % len(EXPERIMENTS)
                elif st["field"] == 5:    # Parameter
                    st["par"] = (st["par"] + step) % len(PARAMETERS)
                elif st["field"] == 6:    # Pair Version
                    st["ver"] = (st["ver"] + step) % len(PAIR_VERSION_CHOICES)
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                participant = st["id"].strip()
                age = st["age"].strip()
                sex = st["sex"].strip()
                level = st["level"].strip()
                pair_version = PAIR_VERSION_CHOICES[st["ver"]]

                if not participant:
                    st["msg"], st["field"] = "Please enter a participant ID.", 0
                elif not (app_dir() / "media").is_dir():
                    st["msg"] = f"Media folder not found. It must be here:\n{app_dir() / 'media'}"
                else:
                    st["msg"] = ""
                    return (participant, age, sex, level,
                            EXPERIMENTS[st["exp"]][1], PARAMETERS[st["par"]][1], pair_version)
            elif e.key == pygame.K_BACKSPACE:
                if st["field"] < len(field_keys):
                    key = field_keys[st["field"]]
                    st[key] = st[key][:-1]
            elif (st["field"] < len(field_keys) and e.unicode and e.unicode.isascii()
                  and (e.unicode.isalnum() or e.unicode in "_- ")):
                key = field_keys[st["field"]]
                if len(st[key]) < 32:
                    st[key] += e.unicode

        draw_menu(screen, fonts, st)
        pygame.display.flip()
        clock.tick(30)


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--pair-version", type=str.lower, default=DEFAULT_PAIR_VERSION,
                    choices=PAIR_VERSION_CHOICES)
    args, _ = ap.parse_known_args()

    default_ver_idx = PAIR_VERSION_CHOICES.index(args.pair_version)
    st = {
        "id": "", "age": "", "sex": "", "level": "",
        "field": 0, "exp": 0, "par": 0, "ver": default_ver_idx, "msg": "",
    }

    while True:
        pygame.init()
        screen = pygame.display.set_mode((900, 620))
        pygame.display.set_caption("MixSon")
        fonts = (pygame.font.Font(None, 56), pygame.font.Font(None, 40), pygame.font.Font(None, 28))
        choice = menu(screen, fonts, st)
        pygame.quit()
        if choice is None:
            return

        participant, age, sex, level, module, parameter, pair_version = choice
        st["msg"] = ""
        try:
            module.Experiment(
                participant, age, sex, level, parameter, pair_version=pair_version
            ).run()
        except SystemExit as e:
            if isinstance(e.code, str):
                st["msg"] = e.code
                log_error(e.code)
        except Exception:
            path = log_error(traceback.format_exc())
            st["msg"] = f"Unexpected error. Details were saved to:\n{path}"


if __name__ == "__main__":
    main()