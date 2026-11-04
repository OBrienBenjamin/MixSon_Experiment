"""MixSon launcher: a small start screen so nobody needs a terminal."""
import textwrap
import traceback
from datetime import datetime

import pygame

from appdir import app_dir
import modality
import strategy

EXPERIMENTS = [("Modality", modality), ("Strategy", strategy)]
PARAMETERS = [("Synch", "synch", "MOS rating 1-5"),
              ("Speed", "speed", "pairwise comparison")]

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
    t = big.render("MixSon experiments", True, FG)
    screen.blit(t, ((W - t.get_width()) // 2, 40))

    cursor = "_" if st["field"] == 0 and (pygame.time.get_ticks() // 500) % 2 == 0 else ""
    exp_name = EXPERIMENTS[st["exp"]][0]
    par_name, _, par_desc = PARAMETERS[st["par"]]
    rows = [("Participant ID", st["id"] + cursor),
            ("Experiment", f"<   {exp_name}   >"),
            ("Parameter", f"<   {par_name}  ({par_desc})   >")]
    y = 140
    for i, (label, value) in enumerate(rows):
        screen.blit(mid.render(label, True, DIM), (70, y))
        screen.blit(mid.render(value, True, ACCENT if st["field"] == i else FG), (330, y))
        y += 70

    hint = small.render("Tab / Up / Down: next field     Left / Right: change     "
                        "Enter: start     Esc: quit", True, DIM)
    screen.blit(hint, ((W - hint.get_width()) // 2, 370))

    if st["msg"]:
        lines = []
        for para in st["msg"].splitlines()[:8]:
            lines += textwrap.wrap(para, 80) or [""]
        y = 410
        for ln in lines[:6]:
            screen.blit(small.render(ln, True, ERR), (70, y))
            y += 24


def menu(screen, fonts, st):
    clock = pygame.time.Clock()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return None
            if e.type != pygame.KEYDOWN:
                continue
            if e.key == pygame.K_ESCAPE:
                return None
            elif e.key in (pygame.K_TAB, pygame.K_DOWN):
                st["field"] = (st["field"] + 1) % 3
            elif e.key == pygame.K_UP:
                st["field"] = (st["field"] - 1) % 3
            elif e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                step = -1 if e.key == pygame.K_LEFT else 1
                if st["field"] == 1:
                    st["exp"] = (st["exp"] + step) % len(EXPERIMENTS)
                elif st["field"] == 2:
                    st["par"] = (st["par"] + step) % len(PARAMETERS)
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                pid = st["id"].strip()
                if not pid:
                    st["msg"], st["field"] = "Please enter a participant ID.", 0
                elif not (app_dir() / "media").is_dir():
                    st["msg"] = f"Media folder not found. It must be here:\n{app_dir() / 'media'}"
                else:
                    st["msg"] = ""
                    return pid, EXPERIMENTS[st["exp"]][1], PARAMETERS[st["par"]][1]
            elif e.key == pygame.K_BACKSPACE:
                if st["field"] == 0:
                    st["id"] = st["id"][:-1]
            elif (st["field"] == 0 and e.unicode and e.unicode.isascii()
                  and (e.unicode.isalnum() or e.unicode in "_-") and len(st["id"]) < 32):
                st["id"] += e.unicode
        draw_menu(screen, fonts, st)
        pygame.display.flip()
        clock.tick(30)


def main():
    st = {"id": "", "field": 0, "exp": 0, "par": 0, "msg": ""}
    while True:
        pygame.init()
        screen = pygame.display.set_mode((900, 520))
        pygame.display.set_caption("MixSon")
        fonts = (pygame.font.Font(None, 56), pygame.font.Font(None, 40), pygame.font.Font(None, 28))
        choice = menu(screen, fonts, st)
        pygame.quit()
        if choice is None:
            return
        pid, module, parameter = choice
        st["msg"] = ""
        try:
            module.Experiment(pid, parameter).run()
        except SystemExit as e:                      # e.g. missing or misnamed files
            if isinstance(e.code, str):
                st["msg"] = e.code
                log_error(e.code)
        except Exception:
            path = log_error(traceback.format_exc())
            st["msg"] = f"Unexpected error. Details were saved to:\n{path}"


if __name__ == "__main__":
    main()