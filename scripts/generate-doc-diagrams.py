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

def step_lifecycle():
    s = Svg(960, 650, (
        "One step, from offer to signed record. Six stages run left to right. Offer: the driver lists the steps "
        "that are legal from the run's state. Bind inputs: the driver resolves each named input to entities in "
        "Quipu. Perform: the performer does the work the step asks for and writes its outputs. Check outputs: "
        "the driver tests each output against its contract, and only a pass advances. Sign: the performer's key "
        "binds the step to its inputs, its outputs and the step before. Commit: Quipu accepts the step only if "
        "the run has not moved. Above Perform are the three kinds of performer, and the definition names one for "
        "each step. Code is a declared command run by the driver with no model involved. For an agent, Chaski "
        "sees an unclaimed step and Shantytown starts a short-lived agent of the step's type. For a person, the "
        "step opens an Ask in Seeds, Rikuy shows it and the answer is signed with a passkey. Below the stages is "
        "the run's record in Quipu, one part under each stage: the definition pinned by its digest, the inputs "
        "and the transaction they were read at, the outputs, a verdict for each contract, the signature, and the "
        "run's state and revision. Offer reads the record. Every other stage writes to it."))
    s.text(40, 52, "One step, from offer to signed record", 24, INK, 700)
    s.text(40, 78, "Code decides what may happen next. Agents and people do the work a step asks for.", 14)

    s.text(110, 118, "WHO PERFORMS A STEP", 10, GOLD, 700, spacing="1")
    s.text(262, 118, "the definition names one for each step", 12, DIM)
    performers = [
        ("Code", "A declared command, run by the driver. No model is involved."),
        ("Agent", "Chaski sees an unclaimed step. Shantytown starts a short-lived agent of the step's type."),
        ("Person", "The step opens an Ask in Seeds. Rikuy shows it, and the answer is signed with a passkey."),
    ]
    pxs, pw = [110, 362, 614], 236
    for x, (title, cap) in zip(pxs, performers):
        s.card(x, 130, pw, 100)
        s.text(x + 16, 156, title, 16, INK, 700)
        s.para(x + 16, 178, cap, pw - 30, 12.5)

    xs, w, top, h = [30, 182, 334, 486, 638, 790], 138, 276, 166
    stages = [
        ("DRIVER", "Offer", "shuttle tick", "Lists the steps that are legal from the run's state."),
        ("DRIVER", "Bind inputs", "inputs", "Resolves each named input to entities in Quipu."),
        ("PERFORMER", "Perform", "performer", "Does the work the step asks for and writes its outputs."),
        ("DRIVER", "Check outputs", "outputs", "Tests each output against its contract. Only a pass advances."),
        ("PERFORMER'S KEY", "Sign", "shuttle-signer", "Binds the step to its inputs, its outputs and the step before."),
        ("QUIPU", "Commit", "compare-and-set", "Accepts the step only if the run has not moved."),
    ]
    for x, (role, title, cmd, cap) in zip(xs, stages):
        hot = title == "Perform"
        s.card(x, top, w, h, stroke=PINK if hot else EDGE, sw=1.6 if hot else 1.2)
        s.text(x + 13, top + 24, role, 9, GOLD, 700, spacing="0.8")
        s.text(x + 13, top + 50, title, 15, INK, 700)
        s.text(x + 13, top + 71, cmd, 11, PINK, cls="m")
        s.para(x + 13, top + 94, cap, w - 22, 12)
    for x in xs[:-1]:
        s.path(f"M{x + w + 1} {top + 44} H{x + w + 6}", "pipe")
        s.head(x + w + 13, top + 44, "right", CORAL)

    # Performers feed the Perform stage.
    cx = xs[2] + w / 2
    for x in pxs:
        s.path(f"M{x + pw / 2} 232 V250", "up")
    s.path(f"M{pxs[0] + pw / 2} 250 H{pxs[2] + pw / 2}", "up")
    s.path(f"M{cx} 250 V{top - 10}", "up")
    s.head(cx, top - 2, "down", GOLD)

    rtop = 500
    s.card(30, rtop, 898, 120)
    s.text(46, rtop + 24, "THE RUN'S RECORD IN QUIPU", 10, GOLD, 700, spacing="1")
    record = [
        ("Definition", "Pinned by its digest when the run starts.", "up"),
        ("Inputs", "Which entities, read at which transaction.", "down"),
        ("Outputs", "What the performer wrote.", "down"),
        ("Verdicts", "Pass, fail or unknown for each contract.", "down"),
        ("Signature", "Who signed, and with which key.", "down"),
        ("State", "The run's state and its revision.", "down"),
    ]
    for x, (title, cap, way) in zip(xs, record):
        mid = x + w / 2
        if way == "up":
            s.path(f"M{mid} {rtop - 4} V{top + h + 12}", "up")
            s.head(mid, top + h + 3, "up", GOLD)
        else:
            s.path(f"M{mid} {top + h + 4} V{rtop - 12}", "down")
            s.head(mid, rtop - 3, "down", PINK)
        s.text(x + 13, rtop + 52, title, 13.5, INK, 700)
        s.para(x + 13, rtop + 72, cap, w - 20, 11.5)
    s.text(40, 640, "Gold: read from the record or handed to a stage. Pink: written to the record.", 12, DIM)
    return s.render()


DIAGRAMS = {"run-record.svg": run_record, "step-lifecycle.svg": step_lifecycle}

if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for name, build in DIAGRAMS.items():
        (out / name).write_text(build())
        print(f"wrote {out / name}")
