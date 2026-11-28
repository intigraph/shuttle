#!/usr/bin/env python3
"""Generate Shuttle's documentation diagrams as SVG.

Usage: generate-doc-diagrams.py OUTPUT_DIR
Style follows the Quipu README diagrams: dark card, gold and pink accents.
"""
import sys
from html import escape
from pathlib import Path

BG, CARD, EDGE = "#12121f", "#20203a", "#2e2e4d"
INK, BODY, GOLD, PINK, CORAL, DIM = "#ecebf5", "#a7a6c2", "#ffc24d", "#ff4fa0", "#ff8a70", "#6f6e8f"

STYLE = """
    .t{font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif}
    .m{font-family:JetBrains Mono,Menlo,Consolas,monospace}
    .card{fill:#20203a;stroke:#2e2e4d}
    .pipe{stroke:#ff8a70;stroke-width:2.5;fill:none;stroke-dasharray:6 6;opacity:.75;animation:flow 1.2s linear infinite}
    .up{stroke:#ffc24d;stroke-width:2;fill:none;stroke-dasharray:4 5;opacity:.8;animation:flow 1.6s linear infinite}
    .down{stroke:#ff4fa0;stroke-width:2;fill:none;stroke-dasharray:4 5;opacity:.8;animation:flow 1.6s linear infinite reverse}
    @keyframes flow{to{stroke-dashoffset:-24}}
    @media (prefers-reduced-motion: reduce){.pipe,.up,.down{animation:none}}
"""


def wrap(text, width, size, mono=False):
    per = size * (0.6 if mono else 0.53)
    limit = max(4, int(width / per))
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > limit:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


class Svg:
    def __init__(self, w, h, label):
        self.w, self.h, self.label, self.out = w, h, label, []

    def add(self, s):
        self.out.append(s)

    def text(self, x, y, s, size=13, fill=BODY, weight=None, cls="t", anchor=None, spacing=None, italic=False):
        attrs = f'class="{cls}" x="{x}" y="{y}" fill="{fill}" font-size="{size}"'
        if weight:
            attrs += f' font-weight="{weight}"'
        if anchor:
            attrs += f' text-anchor="{anchor}"'
        if spacing:
            attrs += f' letter-spacing="{spacing}"'
        if italic:
            attrs += ' font-style="italic"'
        self.add(f"  <text {attrs}>{escape(s)}</text>")

    def para(self, x, y, s, width, size=12.5, fill=BODY, lead=None, cls="t", weight=None, anchor=None):
        lead = lead or round(size * 1.38, 1)
        for n, line in enumerate(wrap(s, width, size, cls == "m")):
            self.text(x, round(y + n * lead, 1), line, size, fill, weight, cls, anchor)
        return y + len(wrap(s, width, size, cls == "m")) * lead

    def card(self, x, y, w, h, stroke=EDGE, fill=CARD, dash=None, rx=14, sw=1.2):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def path(self, d, cls):
        self.add(f'  <path class="{cls}" d="{d}"/>')

    def head(self, x, y, direction, fill):
        pts = {"right": f"{x},{y} {x-9},{y-5} {x-9},{y+5}", "left": f"{x},{y} {x+9},{y-5} {x+9},{y+5}",
               "up": f"{x},{y} {x-5},{y+9} {x+5},{y+9}", "down": f"{x},{y} {x-5},{y-9} {x+5},{y-9}"}[direction]
        self.add(f'  <polygon points="{pts}" fill="{fill}"/>')

    def render(self):
        body = "\n".join(self.out)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" role="img" '
                f'aria-label="{escape(self.label, quote=True)}">\n  <style>{STYLE}  </style>\n'
                f'  <rect width="{self.w}" height="{self.h}" rx="20" fill="{BG}"/>\n{body}\n</svg>\n')


def run_record():
    s = Svg(960, 560, (
        "How a run becomes a record you can check. On the left, three things can take a step: a person or an "
        "agent with shuttle advance, a Seeds work item through shuttle reconcile, and a Chaski schedule through "
        "shuttle scheduled. Each step enters Shuttle on the machine where it happens. Shuttle checks that the "
        "step is legal from the run's state and otherwise refuses it, signs it with the key of whoever took it, "
        "and appends it to a local log. shuttle export sends the log to Quipu, which holds this month's graph of "
        "runs and signed transitions, the frozen months that stay queryable, and the public keys a person "
        "registered. shuttle verify reads the run back from Quipu and checks every signature. Shantytown, a "
        "dashboard or your own query reads runs from Quipu and never calls Shuttle."))
    s.text(40, 52, "How a run becomes a record you can check", 24, INK, 700)
    s.text(40, 78, "A step is checked and signed on the machine where it happens. The record lives in Quipu, "
                   "where anyone can check it.", 14)

    s.text(30, 122, "WHO TAKES A STEP", 10, GOLD, 700, spacing="1")
    s.text(290, 122, "SHUTTLE, ON THIS MACHINE", 10, GOLD, 700, spacing="1")
    s.text(650, 122, "QUIPU", 10, GOLD, 700, spacing="1")

    takers = [
        ("A person or an agent", "shuttle advance", "Names the step it took."),
        ("A Seeds work item", "shuttle reconcile", "The step advances when the item closes."),
        ("A Chaski schedule", "shuttle scheduled", "Each occurrence is one signed run."),
    ]
    for n, (who, cmd, cap) in enumerate(takers):
        y = 136 + n * 128
        s.card(30, y, 220, 110)
        s.text(46, y + 28, who, 15, INK, 700)
        s.text(46, y + 50, cmd, 12, PINK, cls="m")
        s.para(46, y + 74, cap, 196, 12.5)
        s.path(f"M252 {y + 55} H280", "pipe")
        s.head(288, y + 55, "right", CORAL)

    s.card(290, 136, 260, 366, stroke=PINK, sw=1.6)
    steps = [
        ("1", "Check", "Is the step legal from the run's state? If not, refuse it and name the steps that are."),
        ("2", "Sign", "With the ed25519 key of whoever took the step."),
        ("3", "Append", "One line in an append-only log. A run's state is that log, replayed."),
    ]
    for n, (num, title, cap) in enumerate(steps):
        y = 152 + n * 116
        s.card(306, y, 228, 102, fill=BG, rx=10)
        s.text(322, y + 28, num, 13, GOLD, 700, cls="m")
        s.text(342, y + 28, title, 16, INK, 700)
        s.para(322, y + 50, cap, 200, 12.5)
        if n < 2:
            s.path(f"M420 {y + 104} V{y + 108}", "pipe")
            s.head(420, y + 115, "down", CORAL)

    s.card(650, 136, 280, 250)
    rows = [
        ("This month's graph", "Runs and signed transitions."),
        ("Frozen months", "Read-only, and still queryable."),
        ("Public keys", "A person registers them."),
    ]
    for n, (title, cap) in enumerate(rows):
        y = 152 + n * 76
        s.card(666, y, 248, 62, fill=BG, rx=10)
        s.text(682, y + 25, title, 14, INK, 700)
        s.text(682, y + 46, cap, 12.5)

    s.path("M552 200 H640", "pipe")
    s.head(648, 200, "right", CORAL)
    s.text(600, 190, "export", 12, CORAL, cls="m", anchor="middle")
    s.path("M648 330 H562", "down")
    s.head(552, 330, "left", PINK)
    s.text(600, 320, "verify", 12, PINK, cls="m", anchor="middle")

    s.path("M790 388 V402", "down")
    s.head(790, 410, "down", PINK)
    s.card(650, 412, 280, 90)
    s.text(666, 436, "WHO READS THE RECORD", 10, GOLD, 700, spacing="1")
    s.para(666, 458, "Shantytown, a dashboard or your own query. They read runs from Quipu and never call Shuttle.",
           252, 12.5)
    s.text(40, 536, "Nothing runs in the background: a person, an agent or a timer makes each call.", 12.5, DIM)
    return s.render()


DIAGRAMS = {"run-record.svg": run_record}

if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, build in DIAGRAMS.items():
        (out / name).write_text(build())
        print(f"wrote {out / name}")
