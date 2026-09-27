"""
Step vs Chain Growth Lab
------------------------
An interactive Streamlit tool that lets undergraduates *predict* each step of
  (1) PET step-growth polymerisation (terephthalic acid + ethylene glycol), and
  (2) styrene free-radical chain-growth polymerisation (AIBN initiator),
then reveal an animated schematic + explanation.
Version 2: each route has a 10-question bank (5 learning-order slots x 2).
Every attempt draws one question per slot and shuffles the answer options.
Version 3: calculation questions get random numbers each attempt; simulators use
per-run random seeds and a replicate panel to show run-to-run scatter. A final "mystery" challenge
asks students to classify two unlabelled processes from mechanistic evidence.

Run:  pip install streamlit pandas altair
      streamlit run app.py
"""

import math
import random
import re

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Step vs Chain Growth Lab", layout="wide")

# =============================================================================
# 1. Drawing helpers (pure SVG, no external chemistry libraries)
# =============================================================================
COL = {
    "T": "#2563eb",   # terephthaloyl unit  -OC-C6H4-CO-
    "E": "#f59e0b",   # ethylene glycol unit -O-CH2CH2-O-
    "S": "#16a34a",   # styrene repeat unit  -CH2-CH(Ph)-
    "M": "#86efac",   # styrene monomer      CH2=CH-Ph
    "I": "#7c3aed",   # initiator fragment   (CH3)2C(CN)-
    "G1": "#9ca3af",  # mystery unit, light grey
    "G2": "#4b5563",  # mystery unit, dark grey
    "G3": "#6b7280",  # mystery unit, mid grey
    "B": "#64748b",   # benzoyl end-cap (monofunctional acid)
    "X": "#cbd5e1",   # solvent molecule (chain transfer)
    "N": "#0d9488",   # TEMPO nitroxide
}
LBL = {"T": "T", "E": "E", "S": "S", "M": "St", "I": "I", "B": "Bz", "X": "Sol", "N": "NO",
       "G1": "", "G2": "", "G3": ""}
TXT = {"M": "#14532d", "X": "#0f172a"}

BASE_CSS = """
<style>
 body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;}
 .rad{animation:pulse .8s infinite alternate}
 @keyframes pulse{from{opacity:.35}to{opacity:1}}
 .cap{font-size:14px;padding:8px 12px;border-radius:8px;margin:4px 8px;line-height:1.35}
 .ok{background:#ecfdf5;border-left:5px solid #16a34a;color:#064e3b}
 .no{background:#fef2f2;border-left:5px solid #dc2626;color:#7f1d1d}
 .ttl{font-weight:600;font-size:13px;color:#334155;margin:6px 10px 0}
</style>
"""


def _end_width(end):
    if not end:
        return 0
    if end.startswith("@") or end in ("*", "•"):
        return 16
    return 7.4 * len(end) + 6


def species_svg(sp, x, y, r=13, gap=30):
    """Return (svg_string, width) for one molecule drawn as a bead chain.

    sp keys: units (list), left/right (end-group text, '•' radical,
    '*' mystery active end, '@A'/'@B' mystery functional tabs),
    link (text over first bond), tag (text under molecule)."""
    units = sp["units"]
    n = len(units)
    left, right = sp.get("left", ""), sp.get("right", "")
    lw, rw = _end_width(left), _end_width(right)
    cx0 = x + lw + r
    cxl = cx0 + gap * (n - 1)
    out = []
    if n > 1:
        out.append(f'<line x1="{cx0}" y1="{y}" x2="{cxl}" y2="{y}" '
                   f'stroke="#94a3b8" stroke-width="4"/>')
    for i, u in enumerate(units):
        cx = cx0 + gap * i
        out.append(f'<circle cx="{cx}" cy="{y}" r="{r}" fill="{COL[u]}" '
                   f'stroke="#1e293b" stroke-width="1"/>')
        if LBL[u]:
            out.append(f'<text x="{cx}" y="{y + 4}" font-size="11" font-weight="700" '
                       f'text-anchor="middle" fill="{TXT.get(u, "white")}">{LBL[u]}</text>')
    if sp.get("link") and n > 1:
        out.append(f'<text x="{cx0 + gap / 2}" y="{y - 17}" font-size="11" '
                   f'text-anchor="middle" fill="#475569">{sp["link"]}</text>')
    if sp.get("tag"):
        mid = (cx0 + cxl) / 2
        out.append(f'<text x="{mid}" y="{y + 29}" font-size="10" '
                   f'text-anchor="middle" fill="#475569">{sp["tag"]}</text>')

    def end(label, cx, side):
        if not label:
            return
        ex = cx - r - 8 if side == "L" else cx + r + 8
        if label == "•":
            out.append(f'<circle class="rad" cx="{ex}" cy="{y}" r="6" fill="#dc2626"/>')
        elif label == "*":
            pts = []
            for k in range(10):
                ang = math.pi / 2 + k * math.pi / 5
                rr = 8 if k % 2 == 0 else 3.5
                pts.append(f"{ex + rr * math.cos(ang):.1f},{y - rr * math.sin(ang):.1f}")
            out.append(f'<polygon class="rad" points="{" ".join(pts)}" fill="#f97316"/>')
        elif label == "@A":
            out.append(f'<rect x="{ex - 5}" y="{y - 5}" width="10" height="10" fill="#a855f7"/>')
        elif label == "@B":
            out.append(f'<polygon points="{ex},{y - 6} {ex + 6},{y} {ex},{y + 6} {ex - 6},{y}" '
                       f'fill="#14b8a6"/>')
        else:
            anchor = "end" if side == "L" else "start"
            tx = cx - r - 3 if side == "L" else cx + r + 3
            out.append(f'<text x="{tx}" y="{y + 4}" font-size="12" text-anchor="{anchor}" '
                       f'fill="#0f172a">{label}</text>')

    end(left, cx0, "L")
    end(right, cxl, "R")
    width = lw + 2 * r + gap * (n - 1) + rw
    return "".join(out), width


def pot_svg(items, width=700, title=None):
    """Draw a reactor 'pot' snapshot. items = list of (species, count)."""
    x, y, row_h = 34, 36, 58
    parts = []
    for sp, cnt in items:
        _, w = species_svg(sp, 0, 0)
        w_total = w + (34 if cnt > 1 else 12)
        if x + w_total > width - 10:
            x, y = 34, y + row_h
        s, _ = species_svg(sp, x, y)
        parts.append(s)
        if cnt > 1:
            parts.append(f'<text x="{x + w + 4}" y="{y + 5}" font-size="13" '
                         f'fill="#334155">×{cnt}</text>')
        x += w_total
    h = y + 34
    ttl = f'<div class="ttl">{title}</div>' if title else ""
    svg = (f'{ttl}<svg width="{width}" height="{h}" style="background:#f8fafc;'
           f'border:1px solid #e2e8f0;border-radius:10px;margin:4px 8px">{"".join(parts)}</svg>')
    return svg, h + (22 if title else 0)


# ----------------------------------------------------------------------------
# Animated reaction schematic (CSS keyframes inside an SVG)
# ----------------------------------------------------------------------------
def anim_html(spec, nonce=0, W=720, H=140):
    y = 64
    kind = spec["kind"]
    dur = 3.6
    body, css = [], []

    def kf(name, frames):
        css.append(f"@keyframes {name}{{{frames}}}")

    if kind in ("combine", "bounce"):
        a, b = spec["reactants"]
        _, wa = species_svg(a, 0, y)
        _, wb = species_svg(b, 0, y)
        xa, xb = 16, W - 16 - wb
        dxa = max(0, W / 2 - 14 - (xa + wa))
        dxb = min(0, W / 2 + 14 - xb)
        sa, _ = species_svg(a, xa, y)
        sb, _ = species_svg(b, xb, y)
        body.append(f'<g class="ra">{sa}</g><g class="rb">{sb}</g>')
        if kind == "combine":
            kf("ma", f"0%{{transform:translateX(0);opacity:1}}45%{{transform:translateX({dxa}px);opacity:1}}"
                     f"56%{{transform:translateX({dxa}px);opacity:0}}100%{{transform:translateX({dxa}px);opacity:0}}")
            kf("mb", f"0%{{transform:translateX(0);opacity:1}}45%{{transform:translateX({dxb}px);opacity:1}}"
                     f"56%{{transform:translateX({dxb}px);opacity:0}}100%{{transform:translateX({dxb}px);opacity:0}}")
            p = spec["product"]
            _, wp = species_svg(p, 0, y)
            sp_, _ = species_svg(p, (W - wp) / 2, y)
            body.append(f'<g class="prod">{sp_}</g>')
            body.append(f'<circle class="flash" cx="{W / 2}" cy="{y}" r="20" fill="#fde047"/>')
        else:  # bounce = forbidden encounter
            kf("ma", f"0%{{transform:translateX(0)}}42%{{transform:translateX({dxa * 0.55}px)}}"
                     f"100%{{transform:translateX(0)}}")
            kf("mb", f"0%{{transform:translateX(0)}}42%{{transform:translateX({dxb * 0.55}px)}}"
                     f"100%{{transform:translateX(0)}}")
            body.append(f'<text class="nox" x="{W / 2}" y="{y + 12}" font-size="40" '
                        f'text-anchor="middle" fill="#dc2626" font-weight="700">✗</text>')
            css.append(".nox{opacity:0;animation:nox %ss ease forwards}" % dur)
            kf("nox", "0%{opacity:0}40%{opacity:0}48%{opacity:1}100%{opacity:1}")
        css.append(f".ra{{animation:ma {dur}s ease-in-out forwards}}"
                   f".rb{{animation:mb {dur}s ease-in-out forwards}}")

    elif kind == "split":
        a = spec["reactants"][0]
        p1, p2 = spec["products"]
        _, wa = species_svg(a, 0, y)
        _, w1 = species_svg(p1, 0, y)
        _, w2 = species_svg(p2, 0, y)
        m1 = max(0, min(150, W / 2 - 16 - w1 - 10))      # keep products inside the frame
        m2 = max(0, min(150, W / 2 - 16 - w2 - 10))
        s_a, _ = species_svg(a, (W - wa) / 2, y)
        s1, _ = species_svg(p1, W / 2 - 16 - w1, y)
        s2, _ = species_svg(p2, W / 2 + 16, y)
        body.append(f'<g class="ra">{s_a}</g><g class="p1">{s1}</g><g class="p2">{s2}</g>')
        body.append(f'<circle class="flash" cx="{W / 2}" cy="{y}" r="20" fill="#fde047"/>')
        kf("ma", "0%{opacity:1}38%{opacity:1}48%{opacity:0}100%{opacity:0}")
        kf("mp1", "0%{opacity:0;transform:translateX(0)}45%{opacity:0;transform:translateX(0)}"
                  f"55%{{opacity:1}}100%{{opacity:1;transform:translateX(-{m1}px)}}")
        kf("mp2", "0%{opacity:0;transform:translateX(0)}45%{opacity:0;transform:translateX(0)}"
                  f"55%{{opacity:1}}100%{{opacity:1;transform:translateX({m2}px)}}")
        css.append(f".ra{{animation:ma {dur}s forwards}}.p1{{animation:mp1 {dur}s ease-out forwards}}"
                   f".p2{{animation:mp2 {dur}s ease-out forwards}}")

    # shared: flash, product fade-in, by-product rising
    css.append(f".flash{{opacity:0;animation:fl {dur}s forwards}}")
    kf("fl", "0%{opacity:0}40%{opacity:0}49%{opacity:.9}62%{opacity:0}100%{opacity:0}")
    css.append(f".prod{{opacity:0;animation:pr {dur}s forwards}}")
    kf("pr", "0%{opacity:0}52%{opacity:0}68%{opacity:1}100%{opacity:1}")
    if spec.get("byproduct"):
        body.append(f'<text class="bp" x="{W / 2}" y="{y + 44}" font-size="15" font-weight="700" '
                    f'text-anchor="middle" fill="#0369a1">+ {spec["byproduct"]}</text>')
        css.append(f".bp{{opacity:0;animation:bp {dur}s forwards}}")
        kf("bp", "0%{opacity:0;transform:translateY(0)}52%{opacity:0;transform:translateY(0)}"
                 "64%{opacity:1}100%{opacity:1;transform:translateY(22px)}")

    ok = spec.get("allowed", True)
    cap = (f'<div class="cap {"ok" if ok else "no"}"><b>{"Allowed" if ok else "Not a growth step"}:</b> '
           f'{spec["caption"]}</div>')
    uid = f"a{abs(hash(spec['caption'])) % 10**6}"
    css_s, body_s = "".join(css), "".join(body)
    for nm in ("ma", "mb", "mp1", "mp2", "nox", "fl", "pr", "bp", "ra", "rb", "p1", "p2", "flash", "prod"):
        css_s = re.sub(rf"(?<![\w-]){nm}(?![\w-])", f"{nm}_{uid}", css_s)
        body_s = body_s.replace(f'class="{nm}"', f'class="{nm}_{uid}"')
    return (f"<!-- replay {nonce} -->{BASE_CSS}<style>{css_s}</style>"
            f'<svg width="{W}" height="{H}" style="background:#ffffff;border:1px solid #e2e8f0;'
            f'border-radius:10px;margin:4px 8px">{body_s}</svg>{cap}')




# =============================================================================
# 2. Species builders
# =============================================================================
_LEFT = {"T": "HOOC", "E": "HO", "B": "Ph–"}
_RIGHT = {"T": "COOH", "E": "OH", "B": "–Ph"}


def step(units):
    """PET species: T = terephthaloyl, E = ethylene-glycol unit,
    B = benzoyl end-cap (from a monofunctional acid impurity)."""
    units = list(units)
    return {"units": units, "left": _LEFT[units[0]], "right": _RIGHT[units[-1]]}


TPA, EG = step("T"), step("E")
BZA = {"units": ["B"], "left": "Ph–", "right": "COOH", "tag": "benzoic acid"}
STY = {"units": ["M"], "tag": "CH₂=CH–Ph"}
AIBN = {"units": ["I", "I"], "link": "–N=N–", "tag": "AIBN"}
BPO = {"units": ["I", "I"], "link": "–O–O–", "tag": "benzoyl peroxide"}
I_RAD = {"units": ["I"], "right": "•"}
SOLV = {"units": ["X"], "tag": "H–Sol"}
SOL_RAD = {"units": ["X"], "right": "•"}
TEMPO = {"units": ["N"], "left": "•", "tag": "TEMPO"}


def pchain(n, active=True, flip=False, end_h=False):
    """Polystyrene chain: initiator fragment + n styrene units (+ radical end)."""
    u = ["I"] + ["S"] * n
    if flip:
        return {"units": u[::-1], "left": "•" if active else ""}
    return {"units": u, "right": "•" if active else ("H" if end_h else "")}


def dead(n):  # combination product: I-(S)n-I
    return {"units": ["I"] + ["S"] * n + ["I"]}


def dormant(n):  # chain capped by TEMPO (NMP)
    return {"units": ["I"] + ["S"] * n + ["N"], "tag": "dormant (C–O–N)"}


# =============================================================================
# 3. Question bank
#    Each route has 10 questions spread over 5 "slots" that follow the logic of
#    the mechanism (slot 1 → 5). Every attempt draws ONE question per slot, so
#    the 5-question sequence always follows the same learning order but the
#    individual questions differ between attempts.
# =============================================================================
SLOT_NAMES = {
    "pet": {1: "Starting the reaction", 2: "Who can react with whom?", 3: "Conversion and chain length",
            4: "Driving to high molar mass", 5: "Stoichiometry and distribution"},
    "sty": {1: "Initiation", 2: "Adding monomer (propagation)", 3: "Who can react with whom?",
            4: "Chain length vs conversion", 5: "Ending (or controlling) the chain"},
}

PET_BANK = [
    # ---------------- slot 1 · starting the reaction ----------------
    dict(
        id="P1a", slot=1,
        title="What starts the reaction?",
        context=("The reactor contains only **terephthalic acid** (HOOC–C₆H₄–COOH, bead **T**) and "
                 "**ethylene glycol** (HO–CH₂CH₂–OH, bead **E**) at ~250 °C. Each monomer carries "
                 "**two** functional groups."),
        pot=[(TPA, 6), (EG, 6)],
        type="single",
        question="Which reaction builds the PET backbone first?",
        options=["TPA + EG → ester link (–CO–O–) + H₂O",
                 "TPA + TPA join directly through their COOH groups",
                 "An initiator radical must first attack EG",
                 "EG + EG join to start the chain"],
        answer=0,
        explain=("**Esterification**: a COOH group reacts with an OH group, releasing water. This is a "
                 "**polycondensation**: n AA + n BB ⇌ [–AA–BB–]ₙ + (2n − 1) H₂O. No initiator is needed; "
                 "the functional groups themselves are the reactive sites. Acid + acid cannot form an ester. "
                 "*Nuance:* EG + EG can form a diethylene glycol (ether) side product at ~1–2 %, which is a "
                 "defect, not the chain-building step."),
        anims=[
            dict(kind="combine", reactants=[TPA, EG], product=step("TE"), byproduct="H₂O",
                 caption="COOH + HO → ester. The dimer still has one COOH and one OH end, so it can keep reacting."),
            dict(kind="bounce", allowed=False, reactants=[TPA, TPA],
                 caption="COOH + COOH: no complementary partner, so no ester forms."),
        ]),
    dict(
        id="P1b", slot=1,
        title="Why does functionality matter?",
        context=("A batch of TPA is contaminated with a little **benzoic acid** (Ph–COOH, bead **Bz**), "
                 "which has only **one** COOH group."),
        pot=[(TPA, 5), (EG, 6), (BZA, 1)],
        type="single",
        question="What does the benzoic acid do to the polymerisation?",
        options=["It caps a chain end: that end can never react again, so it limits the chain length",
                 "Nothing: it simply reacts like TPA and is built into the backbone",
                 "It acts as an initiator and speeds up growth",
                 "It cross-links the chains into a network"],
        answer=0,
        explain=("Step growth only produces long chains when **every monomer is (at least) difunctional**, "
                 "so that each product still carries two reactive ends. A monofunctional reagent reacts once and "
                 "leaves a non-reactive Ph– end: it is a **chain stopper** (end-capper). Like any stoichiometric "
                 "imbalance, it lowers the maximum Xₙ. (A tri-functional monomer would do the opposite and "
                 "give branching or a network.)"),
        anims=[
            dict(kind="combine", reactants=[BZA, EG], product=step("BE"), byproduct="H₂O",
                 caption="Ph–COOH + HO–E–OH → Ph–CO–O–E–OH. The left end is now permanently unreactive."),
            dict(kind="combine", reactants=[step("BE"), {"units": ["B"], "left": "HOOC", "right": "–Ph"}], product=step("BEB"), byproduct="H₂O",
                 caption="If both ends meet a chain stopper, the molecule is dead: it has no functional group left."),
        ]),

    # ---------------- slot 2 · who can react ----------------
    dict(
        id="P2a", slot=2,
        title="Who can react with whom?",
        context="A few minutes later the pot holds monomers **and** a new dimer HOOC–T–E–OH.",
        pot=[(TPA, 3), (EG, 3), (step("TE"), 3)],
        type="multi",
        question="Select **every** pair that can form a new ester link.",
        options=["Dimer + EG", "Dimer + TPA", "Dimer + Dimer", "TPA + EG",
                 "TPA + TPA", "EG + EG (backbone ester)"],
        answer={0, 1, 2, 3},
        explain=("**Any** molecule with a COOH end can react with **any** molecule with an OH end, whatever "
                 "its size: A + B → AB, AB + A → ABA, AB + AB → ABAB… There is no special 'active centre'. "
                 "This is the defining feature of **step growth**."),
        anims=[
            dict(kind="combine", reactants=[step("TE"), step("TE")], product=step("TETE"), byproduct="H₂O",
                 caption="Oligomer + oligomer: two dimers couple into a tetramer in one step."),
            dict(kind="combine", reactants=[EG, step("TE")], product=step("ETE"), byproduct="H₂O",
                 caption="Monomer + dimer works just as well: EG meets the dimer's COOH end."),
        ]),
    dict(
        id="P2b", slot=2,
        title="Does chain size change reactivity?",
        context=("A tetramer HOOC–(T–E)₂–OH can meet either a small EG molecule or another tetramer. "
                 "Assume the melt is well mixed."),
        pot=[(step("TETE"), 3), (EG, 3), (TPA, 1)],
        type="single",
        question="How does the rate constant per functional group compare in the two cases?",
        options=["About the same: an end group's reactivity does not depend on chain length",
                 "Tetramer + tetramer is far slower because big molecules are unreactive",
                 "Tetramer + EG cannot happen: monomers only react with monomers",
                 "Tetramer + tetramer is far faster because the chains are already activated"],
        answer=0,
        explain=("This is Flory's **equal-reactivity principle**, the assumption behind the Carothers "
                 "kinetics: every COOH has the same rate constant with every OH, whether it sits on a monomer "
                 "or a long chain. That is why the rate law is written simply as "
                 "−d[COOH]/dt = k[COOH][OH][H⁺], without any dependence on chain length. (It breaks down only "
                 "when the melt becomes so viscous that diffusion limits the reaction.)"),
        anims=[
            dict(kind="combine", reactants=[EG, step("TETE")], product=step("ETETE"), byproduct="H₂O",
                 caption="Tetramer + monomer: same COOH + OH chemistry."),
            dict(kind="combine", reactants=[step("TETE"), step("TETE")], product=step("TETETETE"), byproduct="H₂O",
                 caption="Tetramer + tetramer: same chemistry, same k, but chain length doubles in one step."),
        ]),

    # ---------------- slot 3 · conversion and chain length ----------------
    dict(
        id="P3a", slot=3,
        title="How long are the chains?",
        context=("Half of all COOH groups have now reacted (extent of reaction **p = 0.50**). "
                 "Almost no free monomer remains, but look at the chain lengths."),
        pot=[(TPA, 1), (EG, 1), (step("TE"), 3), (step("ETE"), 2), (step("TET"), 2), (step("TETE"), 1)],
        type="single",
        question="What is the number-average degree of polymerisation, Xₙ?",
        options=["Xₙ = 2", "Xₙ ≈ 50", "Xₙ ≈ 100", "Xₙ ≈ 1.5"],
        answer=0,
        explain=("**Carothers equation**: Xₙ = 1 / (1 − p) = 1 / 0.5 = **2**. Monomer is used up early, yet the "
                 "chains are still short. Long chains only appear at the very end, when oligomers join together. "
                 "p = 0.90 gives Xₙ = 10; p = 0.99 gives Xₙ = 100."),
        anims=[
            dict(kind="combine", reactants=[step("TETE"), step("TETE")], product=step("TETETETE"),
                 byproduct="H₂O", caption="Late-stage growth: chain length doubles when two oligomers join."),
        ]),
    dict(
        id="P3b", slot=3,
        title="Counting molecules",
        context=("You start with **16 monomer molecules** (8 TPA + 8 EG). Later you count only **4 molecules** "
                 "in the pot. Every ester bond joins two molecules into one."),
        pot=[(step("TETE"), 1), (step("ETETE"), 1), (step("TET"), 1), (step("TE"), 1)],
        type="single",
        question="What are the conversion p and Xₙ now?",
        options=["p = 0.75 and Xₙ = 4",
                 "p = 0.25 and Xₙ = 1.3",
                 "p = 0.75 and Xₙ = 16",
                 "p = 0.50 and Xₙ = 2"],
        answer=0,
        explain=("Each reaction removes one molecule, so bonds formed = N₀ − Nₜ = 16 − 4 = 12, and "
                 "p = (N₀ − Nₜ)/N₀ = 12/16 = **0.75**. Then Xₙ = N₀/Nₜ = 16/4 = **4**, which matches "
                 "1/(1 − p) = 1/0.25 = 4. To convert to molar mass use Mₙ = M_RU × Xₙ."),
        anims=[
            dict(kind="combine", reactants=[step("TETE"), step("TE")], product=step("TETETE"), byproduct="H₂O",
                 caption="One more bond → one fewer molecule: Nₜ drops from 4 to 3 and Xₙ rises to 16/3 ≈ 5.3."),
        ]),

    # ---------------- slot 4 · driving to high molar mass ----------------
    dict(
        id="P4a", slot=4,
        title="Making bottle-grade PET",
        context=("Bottle-grade PET needs Xₙ of roughly 100 or more. Industrially, a low-molar-mass "
                 "prepolymer with OH (glycol) ends is heated to ~280 °C under vacuum with an Sb catalyst "
                 "(melt polycondensation)."),
        pot=[(step("ETE"), 4), (step("ETETE"), 3)],
        type="multi",
        question="Which conditions are needed to reach high molar mass?",
        options=["Drive p above ≈ 0.99",
                 "Continuously remove the small molecule (H₂O / EG) under vacuum",
                 "Keep the COOH : OH balance very close to 1 : 1",
                 "Add more radical initiator",
                 "Cool the melt so chains stop breaking"],
        answer={0, 1, 2},
        explain=("Polycondensation turns 2 molecules into 2 molecules, so ΔS is small and the reaction is an "
                 "**equilibrium**: the small molecule must be removed (Le Chatelier) to push p → 1. High "
                 "conversion is essential (Carothers), and any imbalance of functional groups caps the chain "
                 "ends. There is no initiator in step growth. In the melt stage, a glycol OH end attacks an ester "
                 "near another chain end and **releases EG**."),
        anims=[
            dict(kind="combine", reactants=[step("ETE"), step("ETE")], product=step("ETETE"),
                 byproduct="HOCH₂CH₂OH ↑ (vacuum)",
                 caption="Transesterification: two glycol-ended chains join and expel ethylene glycol, which is pumped away."),
        ]),
    dict(
        id="P4b", slot=4,
        title="Chain length vs time",
        context=("The esterification is run with an added acid catalyst at constant [H⁺] and equal "
                 "[COOH] = [OH]. From the lecture: 1/(1 − p) = c₀k′t + 1, with k′ = k[H⁺]. "
                 "At t = 0, Xₙ = 1; after **1 h**, Xₙ = **11**."),
        pot=[(step("TETE"), 2), (step("TETETE"), 1), (step("ETE"), 2)],
        type="single",
        question="What is Xₙ after 3 h (same conditions)?",
        options=["Xₙ = 31", "Xₙ = 33", "Xₙ = 121", "Xₙ = 20"],
        answer=0,
        explain=("Xₙ = 1/(1 − p) = c₀k′t + 1, so Xₙ grows **linearly with time**. From 1 h: c₀k′ = 10 h⁻¹, "
                 "so at 3 h Xₙ = 10 × 3 + 1 = **31** (not 3 × 11). The rate law behind it is second order in "
                 "functional groups: −dc/dt = k[H⁺]c². Because high Xₙ needs p very close to 1, reaching "
                 "Xₙ ≈ 100 takes about 10 h here."),
        anims=[
            dict(kind="combine", reactants=[step("TETE"), step("TETETE")], product=step("TETETETETE"),
                 byproduct="H₂O", caption="Rate ∝ k[COOH][OH][H⁺]: each coupling uses one COOH and one OH."),
        ]),

    # ---------------- slot 5 · stoichiometry & distribution ----------------
    dict(
        id="P5a", slot=5,
        title="The cost of imbalance",
        context="Suppose you weigh out a **1 mol % excess of EG**, so the ratio of groups is r = N_COOH/N_OH = 0.99.",
        pot=[(TPA, 5), (EG, 5)],
        type="single",
        question="Even if every COOH reacts (p = 1), what is the maximum Xₙ?",
        options=["Xₙ ≈ 199", "Xₙ → ∞", "Xₙ ≈ 100", "Xₙ ≈ 99"],
        answer=0,
        explain=("Modified Carothers: Xₙ = (1 + r) / (1 + r − 2rp). At p = 1: Xₙ = (1 + r)/(1 − r) = 1.99/0.01 "
                 "= **199**. Once all the COOH is consumed, every chain has OH at both ends and **no complementary "
                 "partner is left**. (Lecture example: r = 0.5 and p = 0.99 gives only Xₙ = 2.94, i.e. trimers.)"),
        anims=[
            dict(kind="bounce", allowed=False, reactants=[step("ETETE"), step("ETE")],
                 caption="OH end + OH end: both chains are 'capped' by the excess glycol, so growth stops."),
        ]),
    dict(
        id="P5b", slot=5,
        title="How broad is the distribution?",
        context=("A perfectly balanced PET synthesis is stopped at **p = 0.99**. "
                 "From the lecture: Xw = (1 + p)/(1 − p) and dispersity Đ = Xw/Xₙ = 1 + p."),
        pot=[(step("TE"), 1), (step("TETE"), 2), (step("TETETE"), 1), (step("TETETETE"), 1)],
        type="single",
        question="Which set of values is correct?",
        options=["Xₙ = 100, Xw = 199, Đ ≈ 1.99",
                 "Xₙ = 100, Xw = 100, Đ = 1.00",
                 "Xₙ = 99, Xw = 199, Đ ≈ 2.0",
                 "Xₙ = 100, Xw = 10 000, Đ = 100"],
        answer=0,
        explain=("Xₙ = 1/0.01 = **100**; Xw = 1.99/0.01 = **199**; Đ = 1 + p = **1.99**. The mixture starts "
                 "monodisperse (all monomer, Đ = 1) and approaches **Đ = 2** at full conversion, because chains "
                 "of every length keep coupling at random. Compare: a controlled/living chain growth can give "
                 "Đ close to 1."),
        anims=[
            dict(kind="combine", reactants=[step("TE"), step("TETETE")], product=step("TETETETE"),
                 byproduct="H₂O", caption="Random coupling of short and long chains broadens the distribution."),
        ]),
]

STY_BANK = [
    # ---------------- slot 1 · initiation ----------------
    dict(
        id="S1a", slot=1,
        title="What starts the reaction?",
        context=("The reactor contains **styrene** (CH₂=CH–Ph, bead **St**) and a small amount of "
                 "**AIBN** initiator at 70 °C."),
        pot=[(STY, 12), (AIBN, 1)],
        type="single",
        question="Which event happens first?",
        options=["AIBN decomposes into two radicals + N₂",
                 "Two styrene molecules join directly by a condensation",
                 "Styrene loses H₂O to form a double bond",
                 "A radical attacks polystyrene that is already present"],
        answer=0,
        explain=("**Initiation part 1** (rate constant k_d): the C–N bonds of AIBN break homolytically on "
                 "heating to give two 2-cyano-2-propyl radicals and N₂ gas. Only a fraction *f* ≈ 0.5–0.7 of "
                 "these radicals escape the solvent cage to start chains. Styrene monomers cannot link to each "
                 "other without a reactive centre. *Nuance:* above ~100 °C styrene can self-initiate thermally."),
        anims=[
            dict(kind="split", reactants=[AIBN], products=[I_RAD, I_RAD], byproduct="N₂ ↑",
                 caption="Homolysis gives two initiating radicals, the only species that can start chains."),
            dict(kind="bounce", allowed=False, reactants=[STY, STY],
                 caption="Monomer + monomer: no radical, no reaction."),
        ]),
    dict(
        id="S1b", slot=1,
        title="Choosing an initiator",
        context="You want to polymerise styrene by a **free-radical** mechanism.",
        pot=[(STY, 10), (BPO, 1)],
        type="multi",
        question="Select **every** compound that would work as a free-radical initiator.",
        options=["AIBN (an azo compound)",
                 "Benzoyl peroxide (BPO)",
                 "Ethylene glycol",
                 "H₂SO₄ / a Lewis acid such as SnCl₄",
                 "Terephthalic acid"],
        answer={0, 1},
        explain=("Common radical initiators are **azo compounds and peroxides**: both contain a weak bond "
                 "(C–N or O–O) that breaks homolytically on heating. Protic or Lewis acids are **cationic** "
                 "initiators: styrene can also be polymerised cationically (and anionically, e.g. with BuLi), "
                 "but that is a different mechanism with a carbocation chain end. Diols and diacids are step-growth "
                 "monomers, not initiators."),
        anims=[
            dict(kind="split", reactants=[BPO], products=[I_RAD, I_RAD],
                 caption="BPO: the weak O–O bond splits into two benzoyloxy radicals (which may lose CO₂)."),
        ]),

    # ---------------- slot 2 · propagation ----------------
    dict(
        id="S2a", slot=2,
        title="Where does the radical add?",
        context="An initiator radical R• meets a styrene molecule CH₂=CH–Ph.",
        pot=[(I_RAD, 1), (STY, 8)],
        type="single",
        question="Which carbon does R• attack, and why?",
        options=["The CH₂ carbon, giving a benzylic radical stabilised by the phenyl ring",
                 "The CH(Ph) carbon, giving a primary radical on CH₂",
                 "The phenyl ring, removing aromaticity",
                 "Neither: R• abstracts H to form an ester"],
        answer=0,
        explain=("Addition to the unsubstituted CH₂ end (rate constant kᵢ) gives **R–CH₂–C•H–Ph**, a benzylic "
                 "radical delocalised into the ring. This regioselectivity makes the polymer **head-to-tail**. "
                 "The product is still a radical: the active centre has **moved** to the chain end."),
        anims=[
            dict(kind="combine", reactants=[I_RAD, STY], product=pchain(1), caption=
                 "Initiation part 2: R• + CH₂=CHPh → R–CH₂–CH(Ph)•. The radical is carried at the new chain end."),
        ]),
    dict(
        id="S2b", slot=2,
        title="How fast does the chain grow?",
        context="Growing polystyryl radicals P• are adding styrene one unit at a time.",
        pot=[(pchain(3), 2), (STY, 10)],
        type="single",
        question="Which rate law describes propagation?",
        options=["R_p = k_p[M][P•]: depends on monomer and on the (tiny) radical concentration",
                 "R_p = k[COOH][OH][H⁺], as in polyesterification",
                 "R_p = k_p[M]²: two monomers must collide",
                 "R_p is independent of [M] because the radical does all the work"],
        answer=0,
        explain=("Each propagation step is one radical + one monomer, so R_p = k_p[M][P•]. k_p for styrene is "
                 "large (≈ 340 L mol⁻¹ s⁻¹ at 60 °C) but [P•] is only ~10⁻⁸ mol L⁻¹, so the chain grows very "
                 "quickly while monomer is consumed gradually. In step growth the rate law involves the "
                 "functional groups of **all** molecules instead."),
        anims=[
            dict(kind="combine", reactants=[pchain(3), STY], product=pchain(4),
                 caption="Propagation: P• + M → P–M•. The radical 'moves' to the new chain end each time."),
        ]),

    # ---------------- slot 3 · who can react ----------------
    dict(
        id="S3a", slot=3,
        title="Who can react with whom?",
        context="Now the pot has growing radical chains (red dot), lots of styrene and some finished ('dead') polystyrene.",
        pot=[(STY, 10), (pchain(4), 2), (dead(8), 1), (I_RAD, 1)],
        type="multi",
        question="Select **every** reaction that can occur.",
        options=["Growing chain• + styrene", "Growing chain• + growing chain•",
                 "Initiator radical R• + styrene", "Styrene + styrene",
                 "Dead polystyrene + styrene", "Dead polystyrene + dead polystyrene"],
        answer={0, 1, 2},
        explain=("Only species with a **radical** can react: propagation (chain• + monomer), termination "
                 "(chain• + chain•) and new initiation (R• + monomer). Dead chains and monomers are inert towards "
                 "each other. Compare with PET, where *every* molecule is reactive."),
        anims=[
            dict(kind="combine", reactants=[pchain(4), STY], product=pchain(5),
                 caption="Propagation: monomer adds one at a time; the radical stays at the chain end."),
            dict(kind="bounce", allowed=False, reactants=[dead(4), STY],
                 caption="Dead chain + monomer: no active centre, so no reaction."),
            dict(kind="bounce", allowed=False, reactants=[STY, STY],
                 caption="Monomer + monomer: still no reaction without a radical."),
        ]),
    dict(
        id="S3b", slot=3,
        title="Chain transfer",
        context=("The polymerisation is run in a solvent with an easily abstracted hydrogen (H–Sol, "
                 "e.g. toluene or a thiol). A growing chain meets a solvent molecule."),
        pot=[(pchain(5), 1), (SOLV, 4), (STY, 8)],
        type="single",
        question="What is the main effect of chain transfer to solvent?",
        options=["The chain stops (gains H), a new radical Sol• starts another chain: shorter chains, rate about unchanged",
                 "Both radicals are destroyed, so the polymerisation stops completely",
                 "The chain keeps growing but becomes branched",
                 "The solvent is built into the backbone as a comonomer"],
        answer=0,
        explain=("Transfer 'moves the radical to something new': P• + H–Sol → P–H + Sol•. The number of radicals "
                 "is unchanged, so the rate barely changes, but each chain is cut short, which **limits the "
                 "molecular weight** (transfer to monomer does the same). Transfer to **polymer** is different: "
                 "it creates a radical on a dead chain and gives **branches** (long branches intermolecularly, "
                 "short ones by intramolecular 'backbiting')."),
        anims=[
            dict(kind="combine", reactants=[pchain(5), SOLV], product=pchain(5, active=False, end_h=True),
                 byproduct="Sol•", caption="Transfer: the growing chain takes H and dies; the radical moves to the solvent."),
            dict(kind="combine", reactants=[SOL_RAD, STY], product={"units": ["X", "S"], "right": "•"},
                 caption="Sol• re-initiates: a new chain starts, so the radical count is conserved."),
        ]),

    # ---------------- slot 4 · chain length vs conversion ----------------
    dict(
        id="S4a", slot=4,
        title="A snapshot at 10 % conversion",
        context="Only 10 % of the styrene has been consumed.",
        pot=[(STY, 18), (dead(14), 1), (pchain(9), 1)],
        type="single",
        question="What does the reactor contain?",
        options=["Mostly monomer, some already-long chains, and a tiny concentration of radicals",
                 "All chains are short oligomers (Xₙ ≈ 1.1)",
                 "No polymer yet: polymer only forms near 100 % conversion",
                 "Mainly dimers and trimers"],
        answer=0,
        explain=("Radical concentration is only ~10⁻⁸ mol L⁻¹, but propagation is fast, so each chain grows to "
                 "**full length within about a second**, then dies. High-molar-mass polymer is present **from the "
                 "start**; conversion rises by forming *more* chains, not by making existing chains longer. This "
                 "is the opposite of step growth, where monomer disappears early but chains stay short."),
        anims=[
            dict(kind="combine", reactants=[pchain(9), STY], product=pchain(10),
                 caption="Each active chain adds thousands of monomers in its short lifetime."),
        ]),
    dict(
        id="S4b", slot=4,
        title="Molar mass vs conversion",
        context=("You sample a free-radical styrene polymerisation at 5 %, 30 % and 60 % conversion "
                 "and measure Mₙ of the polymer (monomer removed)."),
        pot=[(STY, 14), (dead(12), 1), (dead(13), 1), (pchain(8), 1)],
        type="single",
        question="What trend do you expect?",
        options=["Mₙ is already high at 5 % and stays roughly similar (drifting down slowly as [M] falls)",
                 "Mₙ is tiny at 5 % and rises steeply only near 100 %, like the Carothers curve",
                 "Mₙ rises linearly with conversion",
                 "Mₙ doubles every time conversion doubles"],
        answer=0,
        explain=("In conventional free-radical polymerisation each chain is born, grows and dies within about a "
                 "second, so Mₙ is set by the **kinetic chain length** (∝ k_p[M]/[P•]), not by conversion. "
                 "It is high from the start and drifts down slowly as monomer is used up (at high conversion the "
                 "gel effect can push it back up). The steep curve near 100 % is the step-growth signature; a "
                 "**linear** increase is the signature of *controlled/living* chain growth."),
        anims=[
            dict(kind="combine", reactants=[pchain(8), STY], product=pchain(9),
                 caption="Growth happens chain by chain: early chains are already long."),
        ]),

    # ---------------- slot 5 · termination / control ----------------
    dict(
        id="S5a", slot=5,
        title="How does a chain die?",
        context="Two growing polystyryl radicals meet.",
        pot=[(pchain(6), 1), (pchain(5, flip=True), 1), (STY, 6)],
        type="single",
        question="What happens **predominantly** for styrene?",
        options=["Combination: the radicals pair up into one dead chain (head-to-head link)",
                 "Disproportionation dominates, giving two dead chains",
                 "They keep growing as one chain with two radical ends",
                 "They form an ester and release water"],
        answer=0,
        explain=("For polystyrene, termination is **mainly by combination** (k_tc): the two radical ends form a "
                 "C–C bond, giving one dead chain with a head-to-head junction and **twice** the molecular weight. "
                 "Disproportionation (k_td, H-transfer giving one saturated and one unsaturated end) dominates for "
                 "methacrylates such as PMMA. Termination is irreversible. (Contrast: PET chain ends stay reactive.)"),
        anims=[
            dict(kind="combine", reactants=[pchain(6), pchain(5, flip=True)], product=dead(11),
                 caption="Combination: two active centres are destroyed, one long dead chain is formed."),
        ]),
    dict(
        id="S5b", slot=5,
        title="Taming the radical: NMP",
        context=("The same styrene polymerisation is run at ~120 °C with the stable nitroxide **TEMPO** "
                 "(nitroxide-mediated polymerisation, invented in Melbourne in 1986)."),
        pot=[(STY, 10), (pchain(4), 1), (TEMPO, 2)],
        type="single",
        question="What does TEMPO do?",
        options=["It reversibly caps the chain end, keeping [P•] tiny so termination is suppressed: Mₙ grows with conversion and Đ is narrow",
                 "It permanently kills every chain, so no polymer forms",
                 "It turns the reaction into step growth",
                 "It adds to styrene and becomes the main initiator of new chains"],
        answer=0,
        explain=("P• + TEMPO• ⇌ P–TEMPO (dormant). The equilibrium lies to the dormant side, so at any moment "
                 "very few chains are active and radical–radical termination becomes rare. Each chain grows a "
                 "little every time it is activated, so **all chains grow together**: Mₙ increases linearly with "
                 "conversion, Đ is low and chain ends are well defined ('living'-like). ATRP (Cu/Br) and RAFT "
                 "(thiocarbonylthio) use the same idea of reversible capping."),
        anims=[
            dict(kind="combine", reactants=[pchain(6), TEMPO], product=dormant(6),
                 caption="Deactivation: the radical end is capped by TEMPO and becomes dormant."),
            dict(kind="split", reactants=[dormant(6)], products=[pchain(6), TEMPO],
                 caption="Activation (heat): the C–O bond breaks again, the chain adds a few monomers, then is capped again."),
        ]),
]

BANKS = {"pet": PET_BANK, "sty": STY_BANK}
QBYID = {q["id"]: q for bank in BANKS.values() for q in bank}
ROUTE_NAMES = {"pet": "PET: step growth", "sty": "Polystyrene: radical chain growth"}
N_SLOTS = 5

# =============================================================================
# 3b. Randomised numbers for the calculation questions
#     gen(rng) returns fields that overwrite the static text of a question.
#     Every attempt gets fresh numbers, so the 5 calculation questions act as a
#     much larger question bank without adding new questions.
# =============================================================================
def fmt(v, nd=1):
    if v == float("inf"):
        return "∞"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}"
    return f"{v:.{nd}f}"


def _distinct(correct, distractors):
    """Correct option first, then unique distractors (needs 3)."""
    out = [correct]
    for d in distractors:
        if d not in out:
            out.append(d)
    return out[:4]


def gen_p3a(rng):
    p = rng.choice([0.50, 0.60, 0.75, 0.80, 0.90, 0.95, 0.98])
    xn = 1 / (1 - p)
    opts = _distinct(f"Xₙ = {fmt(xn)}",
                     [f"Xₙ = {fmt(1 / p, 2)}", f"Xₙ = {fmt(100 * p)}", f"Xₙ = {fmt(xn ** 2)}",
                      f"Xₙ = {fmt(p / (1 - p) + 10)}"])
    return dict(
        context=(f"The extent of reaction is now **p = {p:.2f}** (fraction of COOH groups that have reacted). "
                 "Look at how much monomer is left and how long the chains are."),
        question="What is the number-average degree of polymerisation, Xₙ?",
        options=opts, answer=0,
        explain=(f"**Carothers equation**: Xₙ = 1 / (1 − p) = 1 / {1 - p:.2f} = **{fmt(xn)}**. "
                 "Monomer is used up early, yet the chains stay short until p is very close to 1: "
                 "p = 0.90 gives Xₙ = 10; p = 0.99 gives Xₙ = 100."))


def gen_p3b(rng):
    for _ in range(50):
        n0 = rng.choice([12, 16, 20, 24, 30, 40])
        nt = rng.choice([d for d in range(2, n0 // 2) if n0 % d == 0 or rng.random() < 0.3])
        p, xn = (n0 - nt) / n0, n0 / nt
        opts = _distinct(f"p = {p:.2f} and Xₙ = {fmt(xn)}",
                         [f"p = {nt / n0:.2f} and Xₙ = {fmt(n0 / (n0 - nt))}",
                          f"p = {p:.2f} and Xₙ = {n0 - nt}",
                          f"p = {p:.2f} and Xₙ = {n0}",
                          f"p = {1 - 2 * nt / n0:.2f} and Xₙ = {fmt(xn / 2)}"])
        if len(opts) == 4:
            break
    return dict(
        context=(f"You start with **{n0} monomer molecules** ({n0 // 2} TPA + {n0 // 2} EG). Later you count only "
                 f"**{nt} molecules** in the pot. Every ester bond joins two molecules into one."),
        question="What are the conversion p and Xₙ now?",
        options=opts, answer=0,
        explain=(f"Each reaction removes one molecule, so bonds formed = N₀ − Nₜ = {n0} − {nt} = {n0 - nt}, and "
                 f"p = (N₀ − Nₜ)/N₀ = {n0 - nt}/{n0} = **{p:.2f}**. Then Xₙ = N₀/Nₜ = {n0}/{nt} = **{fmt(xn)}**, "
                 f"which matches 1/(1 − p). To convert to molar mass use Mₙ = M_RU × Xₙ."))


def gen_p4b(rng):
    for _ in range(50):
        t1 = rng.choice([1, 2])
        slope = rng.choice([4, 5, 6, 8, 10, 12, 15])          # c0·k' in h⁻¹
        a = slope * t1 + 1
        t2 = rng.choice([t for t in (3, 4, 5, 6) if t > t1])
        ans = slope * t2 + 1
        opts = _distinct(f"Xₙ = {ans}",
                         [f"Xₙ = {fmt(a * t2 / t1)}", f"Xₙ = {slope * t2}", f"Xₙ = {a + t2}",
                          f"Xₙ = {fmt(a ** (t2 / t1))}"])
        if len(opts) == 4:
            break
    return dict(
        context=("The esterification is run with an added acid catalyst at constant [H⁺] and equal "
                 "[COOH] = [OH]. From the lecture: 1/(1 − p) = c₀k′t + 1, with k′ = k[H⁺]. "
                 f"At t = 0, Xₙ = 1; after **{t1} h**, Xₙ = **{a}**."),
        question=f"What is Xₙ after {t2} h (same conditions)?",
        options=opts, answer=0,
        explain=(f"Xₙ = 1/(1 − p) = c₀k′t + 1, so Xₙ grows **linearly with time**. From the data: "
                 f"c₀k′ = ({a} − 1)/{t1} = {slope} h⁻¹, so at {t2} h Xₙ = {slope} × {t2} + 1 = **{ans}** "
                 f"(not {fmt(a * t2 / t1)}, which forgets the '+1'). The rate law behind it is second order "
                 "in functional groups: −dc/dt = k[H⁺]c²."))


def gen_p5a(rng):
    for _ in range(50):
        r = rng.choice([0.95, 0.97, 0.98, 0.99, 0.995])
        p = rng.choice([1.0, 1.0, 0.99, 0.98])
        xn = (1 + r) / (1 + r - 2 * r * p)
        ideal = float("inf") if p == 1 else 1 / (1 - p)
        opts = _distinct(f"Xₙ ≈ {fmt(xn)}",
                         [f"Xₙ ≈ {fmt(ideal)}", f"Xₙ ≈ {fmt(1 / (1 - r))}", f"Xₙ ≈ {fmt(xn / 2)}",
                          f"Xₙ ≈ {fmt(r / (1 - r))}"])
        if len(opts) == 4:
            break
    excess = (1 / r - 1) * 100
    pt = "every COOH reacts (p = 1)" if p == 1 else f"p = {p:.2f} (conversion of COOH)"
    return dict(
        context=(f"You weigh out a small excess of EG (≈ {excess:.1f} mol % extra OH groups), so the ratio of groups "
                 f"is **r = N_COOH/N_OH = {r}**."),
        question=f"If {pt}, what is Xₙ?",
        options=opts, answer=0,
        explain=(f"Modified Carothers: Xₙ = (1 + r) / (1 + r − 2rp) = {1 + r:.3f} / ({1 + r:.3f} − 2 × {r} × {p:.2f}) "
                 f"= **{fmt(xn)}**. Without the imbalance it would be {fmt(ideal)}. Once the COOH groups run out, "
                 "chains are capped with OH at both ends and **no complementary partner is left**. "
                 "(Lecture example: r = 0.5 and p = 0.99 gives only Xₙ = 2.94, i.e. trimers.)"))


def gen_p5b(rng):
    p = rng.choice([0.90, 0.95, 0.98, 0.99, 0.995])
    xn, xw, D = 1 / (1 - p), (1 + p) / (1 - p), 1 + p
    opts = _distinct(f"Xₙ = {fmt(xn)}, Xw = {fmt(xw)}, Đ ≈ {D:g}",
                     [f"Xₙ = {fmt(xn)}, Xw = {fmt(xn)}, Đ = 1.00",
                      f"Xₙ = {fmt(xn)}, Xw = {fmt(xn * xn)}, Đ = {fmt(xn)}",
                      f"Xₙ = {fmt(xn - 1)}, Xw = {fmt(xw)}, Đ ≈ 2.0"])
    return dict(
        context=(f"A perfectly balanced PET synthesis is stopped at **p = {p}**. "
                 "From the lecture: Xw = (1 + p)/(1 − p) and dispersity Đ = Xw/Xₙ = 1 + p."),
        question="Which set of values is correct?",
        options=opts, answer=0,
        explain=(f"Xₙ = 1/(1 − p) = **{fmt(xn)}**; Xw = (1 + p)/(1 − p) = **{fmt(xw)}**; Đ = 1 + p = **{D:g}**. "
                 "The mixture starts monodisperse (all monomer, Đ = 1) and approaches **Đ = 2** at full conversion, "
                 "because chains of every length keep coupling at random. A controlled/living chain growth can "
                 "give Đ close to 1."))


GENERATORS = {"P3a": gen_p3a, "P3b": gen_p3b, "P4b": gen_p4b, "P5a": gen_p5a, "P5b": gen_p5b}


def instantiate(q):
    """Return a concrete copy of question q (random numbers filled in if it has a generator)."""
    inst = dict(q)
    if q["id"] in GENERATORS:
        inst.update(GENERATORS[q["id"]](random))
        inst["randomised"] = True
    return inst


# =============================================================================
# 4. Round engine (random draw per attempt + shuffled options)
# =============================================================================
ss = st.session_state
ss.setdefault("nonce", 0)


def new_attempt(key):
    """Draw one question per slot and shuffle every option list.

    - Unseen questions are always preferred, so the whole bank is covered in 2 attempts.
    - After that, each slot is drawn at random, weighted towards less-seen questions.
    - A set identical to the previous attempt is re-drawn."""
    seen = ss.setdefault(f"{key}_seen", {})
    last = ss.get(f"{key}_set", [])
    for _ in range(30):
        chosen = []
        for slot in range(1, N_SLOTS + 1):
            pool = [q["id"] for q in BANKS[key] if q["slot"] == slot]
            unseen = [q for q in pool if seen.get(q, 0) == 0]
            if unseen:
                chosen.append(random.choice(unseen))
            else:
                w = [1 / (1 + seen[q]) for q in pool]
                chosen.append(random.choices(pool, weights=w)[0])
        if chosen != last:
            break
    for q in chosen:
        seen[q] = seen.get(q, 0) + 1
    ss[f"{key}_set"] = chosen
    inst = {qid: instantiate(QBYID[qid]) for qid in chosen}      # fresh numbers each attempt
    ss[f"{key}_inst"] = inst
    ss[f"{key}_order"] = {qid: random.sample(inst[qid]["options"], len(inst[qid]["options"]))
                          for qid in chosen}
    ss[f"{key}_attempt"] = ss.get(f"{key}_attempt", 0) + 1
    ss[f"{key}_idx"] = 0
    ss[f"{key}_res"] = {}


def run_route(key):
    name = ROUTE_NAMES[key]
    if f"{key}_set" not in ss:
        new_attempt(key)
    qset = ss[f"{key}_set"]
    idx = ss[f"{key}_idx"]
    results = ss[f"{key}_res"]
    att = ss[f"{key}_attempt"]

    if idx >= len(qset):
        n_ok = sum(results.values())
        hist = ss.setdefault(f"{key}_hist", {})
        hist[att] = n_ok
        st.success(f"Attempt {att} complete: **{n_ok} / {len(qset)}** predictions correct.")
        st.markdown("Questions in this attempt: " + ", ".join(QBYID[q]["title"] for q in qset))
        st.markdown("Start a new attempt to get a different set of questions (same learning order), "
                    "or try the **Mystery challenge** tab.")
        if st.button("Start a new attempt", type="primary", key=f"{key}_restart{att}"):
            new_attempt(key)
            st.rerun()
        return

    R = ss[f"{key}_inst"][qset[idx]]
    opts = ss[f"{key}_order"][R["id"]]            # shuffled display order
    correct_txt = ({R["options"][R["answer"]]} if R["type"] == "single"
                   else {R["options"][i] for i in R["answer"]})

    st.progress(idx / len(qset),
                text=f"{name} · attempt {att} · question {idx + 1} of {len(qset)} · "
                     f"{SLOT_NAMES[key][R['slot']]}")
    st.subheader(f"Q{idx + 1} · {R['title']}")
    if R.get("randomised"):
        st.caption("Calculation question: the numbers are generated randomly for each attempt.")
    st.markdown(R["context"])
    svg, h = pot_svg(R["pot"], title="Reactor contents")
    components.html(BASE_CSS + svg, height=h + 16)

    answered = idx in results
    qkey = f"{key}_a{att}_q{idx}"
    if R["type"] == "single":
        choice = st.radio(R["question"], opts, index=None, key=qkey, disabled=answered)
    else:
        choice = st.multiselect(R["question"], opts, key=qkey, disabled=answered)
    st.text_input("Your reasoning in one sentence (write it before you reveal):",
                  key=f"{key}_a{att}_why{idx}", disabled=answered)

    if not answered:
        if st.button("Lock in my prediction", type="primary", key=f"{key}_a{att}_lock{idx}"):
            if not choice:
                st.warning("Make a prediction first.")
            else:
                picked = {choice} if R["type"] == "single" else set(choice)
                results[idx] = picked == correct_txt
                st.rerun()
        return

    # ---- reveal ----
    if results[idx]:
        st.success("Correct prediction.")
    else:
        st.error("Not quite. Compare your answer with the mechanism below.")
    if R["type"] == "multi":
        chosen = set(choice or [])
        rows = []
        for opt in opts:
            truth = opt in correct_txt
            rows.append({"Option": opt,
                         "Correct?": "Yes" if truth else "No",
                         "You said": "Yes" if opt in chosen else "No",
                         "": "✓" if (opt in chosen) == truth else "✗"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.markdown(f"**Answer:** {R['options'][R['answer']]}")
    st.info(R["explain"])

    st.markdown("**Animated schematic**")
    for a in R["anims"]:
        components.html(anim_html(a, ss.nonce), height=215)
    c1, c2 = st.columns([1, 4])
    if c1.button("Replay animations", key=f"{key}_a{att}_replay{idx}"):
        ss.nonce += 1
        st.rerun()
    if c2.button("Next question →", type="primary", key=f"{key}_a{att}_next{idx}"):
        ss[f"{key}_idx"] = idx + 1
        st.rerun()


# =============================================================================
# 5. Mystery challenge
# =============================================================================
def mystery_step_panel():
    A = lambda n: {"units": ["G1", "G2"] * (n // 2) + (["G1"] if n % 2 else []),
                   "left": "@A", "right": "@A" if n % 2 else "@B"}
    mA = {"units": ["G1"], "left": "@A", "right": "@A"}
    mB = {"units": ["G2"], "left": "@B", "right": "@B"}
    snaps = [
        ("t₁ (early)", [(mA, 7), (mB, 7)]),
        ("t₂ (middle)", [(mA, 1), (mB, 1), (A(2), 3), (A(3), 2), (A(4), 1)]),
        ("t₃ (late)", [(A(4), 1), (A(6), 1), (A(8), 1), (A(10), 1)]),
    ]
    return snaps


def mystery_chain_panel():
    mon = {"units": ["G3"], "tag": "="}
    live = lambda n: {"units": ["G2"] + ["G1"] * n, "right": "*"}
    deadc = lambda n: {"units": ["G2"] + ["G1"] * n + ["G2"]}
    ini = {"units": ["G2"], "right": "*"}
    snaps = [
        ("t₁ (early)", [(mon, 16), (ini, 1), (live(9), 1)]),
        ("t₂ (middle)", [(mon, 10), (deadc(12), 1), (live(10), 1)]),
        ("t₃ (late)", [(mon, 5), (deadc(12), 2), (deadc(10), 1)]),
    ]
    return snaps


EVIDENCE = [
    ("Monomer is almost gone while chains are still short", "step"),
    ("Monomer is still present at late times", "chain"),
    ("Long chains already exist at early times", "chain"),
    ("All molecules grow gradually and together", "step"),
    ("Only molecules marked with a special active end grow", "chain"),
    ("Any two molecules with matching end groups can join", "step"),
    ("Two large chains can join each other and remain reactive", "step"),
]


def run_mystery():
    st.subheader("Mystery challenge: classify without labels")
    st.markdown(
        "Below are two unnamed reaction processes, each shown at three times. Beads are anonymous units. "
        "Coloured tabs and stars are the only chemical clues:\n"
        "- ■ purple square and ◆ teal diamond: two kinds of functional end groups\n"
        "- ★ orange star: a special reactive end\n\n"
        "Decide which process is **step growth** and which is **chain growth**, and pick the evidence that supports each decision.")
    if "myst_swap" not in ss:
        ss.myst_swap = random.random() < 0.5
    panels = {"step": mystery_step_panel(), "chain": mystery_chain_panel()}
    order = ["chain", "step"] if ss.myst_swap else ["step", "chain"]
    labels = {"X": order[0], "Y": order[1]}

    cols = st.columns(2)
    for col, (lab, mech) in zip(cols, labels.items()):
        with col:
            st.markdown(f"#### Process {lab}")
            html, H = BASE_CSS, 0
            for t, items in panels[mech]:
                svg, h = pot_svg(items, width=520, title=t)
                html += svg
                H += h + 12
            components.html(html, height=H + 10)
            st.selectbox(f"Process {lab} is…", ["—", "Step growth", "Chain growth"], key=f"myst_mech_{lab}")
            st.multiselect(f"Evidence you see in Process {lab}", [e for e, _ in EVIDENCE], key=f"myst_ev_{lab}")

    st.text_area("Explain in 2–3 sentences how the *reactivity of molecules* (not the product name) "
                 "led to your decision:", key="myst_text")

    if st.button("Check my classification", type="primary"):
        ss.myst_checked = True
    if ss.get("myst_checked"):
        tag = dict(EVIDENCE)
        for lab, mech in labels.items():
            guess = ss.get(f"myst_mech_{lab}", "—")
            ev = ss.get(f"myst_ev_{lab}", [])
            right_mech = guess.lower().startswith(mech)
            good = [e for e in ev if tag[e] == mech]
            bad = [e for e in ev if tag[e] != mech]
            msg = f"**Process {lab}** is **{mech} growth**. "
            msg += "Your classification is correct. " if right_mech else "Your classification is incorrect. "
            msg += f"Supporting evidence chosen: {len(good)}"
            if bad:
                msg += f"; evidence that actually points the other way: {', '.join(bad)}"
            (st.success if right_mech and not bad and len(good) >= 2 else st.warning)(msg)
        txt = ss.get("myst_text", "").lower()
        keys = {"active / radical end": ["active", "radical", "star", "centre", "center"],
                "any molecule / end groups": ["any", "end group", "functional", "matching"],
                "monomer persistence / consumption": ["monomer"]}
        hit = [k for k, words in keys.items() if any(w in txt for w in words)]
        miss = [k for k in keys if k not in hit]
        if txt.strip():
            st.markdown(f"Your explanation mentions: {', '.join(hit) or 'none of the key ideas'}."
                        + (f" Consider also discussing: {', '.join(miss)}." if miss else ""))
        with st.expander("Model answer"):
            st.markdown(
                "- **Step growth:** every molecule carries reactive end groups (■ and ◆), so *any* ■ can meet *any* ◆. "
                "Monomer disappears early (t₂) but chains stay short; long chains appear only at t₃ when oligomers "
                "join. Chain ends remain reactive.\n"
                "- **Chain growth:** only molecules with a ★ active end grow, adding monomer one unit at a time. "
                "Long chains exist already at t₁, while monomer is still present at t₃. Chains without ★ are dead "
                "and never react again.")
        if st.button("New mystery (shuffle order)"):
            for k in [k for k in ss.keys() if str(k).startswith("myst")]:
                del ss[k]
            st.rerun()


# =============================================================================
# 6. Compare & simulate
# =============================================================================
def run_compare():
    st.subheader("Chain length vs conversion")
    c1, c2, c3 = st.columns(3)
    r = c1.slider("Step growth: group ratio r (≤ 1)", 0.95, 1.0, 1.0, 0.005)
    p_mark = c2.slider("Mark conversion p", 0.0, 0.99, 0.90, 0.01)
    nu0 = c3.slider("Chain growth: initial Xₙ of chains formed", 200, 5000, 1000, 100)
    xs = [i / 1000 for i in range(0, 996, 5)]
    rows = []
    for p in xs:
        rows.append({"conversion": p, "Xn": (1 + r) / (1 + r - 2 * r * p), "mechanism": "Step growth (PET)"})
        rows.append({"conversion": p, "Xn": max(1, nu0 * (1 - p)), "mechanism": "Chain growth (styrene)"})
    df = pd.DataFrame(rows)
    chart = alt.Chart(df).mark_line(strokeWidth=3).encode(
        x=alt.X("conversion", title="Fractional conversion (p or x)"),
        y=alt.Y("Xn", scale=alt.Scale(type="log"), title="Xₙ (log scale)"),
        color=alt.Color("mechanism", scale=alt.Scale(range=["#16a34a", "#2563eb"])))
    rule = alt.Chart(pd.DataFrame({"p": [p_mark]})).mark_rule(strokeDash=[4, 4]).encode(x="p")
    st.altair_chart(chart + rule, width="stretch")
    xn_step = (1 + r) / (1 + r - 2 * r * p_mark)
    st.markdown(f"At p = **{p_mark:.2f}**: step growth Xₙ = **{xn_step:.1f}**; "
                f"chains formed now in chain growth have Xₙ ≈ **{nu0 * (1 - p_mark):.0f}**.")
    st.caption("Chain-growth curve is idealised: instantaneous Xₙ ∝ [M]/[I]^½ with [I] taken as constant. "
               "Real polystyrene also shows chain transfer and, at high conversion, the gel (Trommsdorff) effect.")

    st.subheader("Side-by-side summary")
    st.dataframe(pd.DataFrame({
        "Feature": ["Which species react?", "Initiator needed?", "Monomer consumption",
                    "High polymer appears", "Chain ends after reaction", "By-product",
                    "Sensitivity to stoichiometry"],
        "Step growth (PET)": ["Any two molecules with complementary groups", "No (catalyst only)",
                              "Early", "Only at p > 0.99", "Still reactive", "H₂O or EG", "Critical"],
        "Chain growth (PS)": ["Only active (radical) chain + monomer", "Yes (AIBN, BPO…)",
                              "Gradual throughout", "Immediately", "Dead after termination", "None",
                              "Not relevant"]}), hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Stochastic simulators. Each run owns its own random.Random(seed), so
#   * two different runs are statistically independent (different histograms),
#   * the same seed reproduces a run exactly (useful for teaching / checking).
# ---------------------------------------------------------------------------
N_STEP = 100                      # 100 A–A + 100 B–B molecules
CH = dict(M0=5000, I0=100, kd=0.01, f=0.6, kp=20.0, kt=0.10, max_ticks=4000)


def new_seed():
    return random.randrange(1, 10**6)


def step_new(seed):
    return {"mols": [[1, "A", "A"] for _ in range(N_STEP)] + [[1, "B", "B"] for _ in range(N_STEP)],
            "bonds": 0, "A0": 2 * N_STEP, "seed": seed, "rng": random.Random(seed)}


def step_bonds(s, k):
    """Form k ester-like bonds between randomly chosen complementary ends."""
    mols, rng = s["mols"], s["rng"]
    for _ in range(k):
        Aend = [(i, e) for i, m in enumerate(mols) for e in (1, 2) if m[e] == "A"]
        Bend = [(i, e) for i, m in enumerate(mols) for e in (1, 2) if m[e] == "B"]
        for _try in range(50):
            if not Aend or not Bend:
                return
            (ia, ea), (ib, eb) = rng.choice(Aend), rng.choice(Bend)
            if ia != ib:           # no cyclisation in this model
                break
        else:
            return
        ma, mb = mols[ia], mols[ib]
        new = [ma[0] + mb[0], ma[3 - ea], mb[3 - eb]]
        for i in sorted((ia, ib), reverse=True):
            mols.pop(i)
        mols.append(new)
        s["bonds"] += 1


def step_run_to(seed, p_target):
    s = step_new(seed)
    step_bonds(s, round(p_target * s["A0"]))
    return s


def chain_new(seed):
    return {"M": CH["M0"], "I": CH["I0"], "active": [], "dead": [], "t": 0,
            "seed": seed, "rng": random.Random(seed)}


def chain_ticks(c, ticks):
    """One tick = initiator decomposition, propagation, termination by combination."""
    rng = c["rng"]
    for _ in range(ticks):
        if c["I"] == 0 and not c["active"]:
            return                       # dead end: no initiator and no radicals left
        c["t"] += 1
        for _ in range(c["I"]):
            if rng.random() < CH["kd"]:
                c["I"] -= 1
                c["active"] += [0 for _ in range(2) if rng.random() < CH["f"]]   # cage effect
        grow = []
        for L in c["active"]:
            mu = CH["kp"] * c["M"] / CH["M0"]
            add = min(c["M"], max(0, round(rng.gauss(mu, math.sqrt(mu) if mu > 0 else 0))))
            c["M"] -= add
            grow.append(L + add)
        rng.shuffle(grow)
        keep = []
        while grow:
            L = grow.pop()
            if grow and rng.random() < CH["kt"]:
                c["dead"].append(L + grow.pop())      # combination
            else:
                keep.append(L)
        c["active"] = keep


def chain_conv(c):
    return 1 - c["M"] / CH["M0"]


def chain_run_to(seed, x_target):
    c = chain_new(seed)
    while chain_conv(c) < x_target and c["t"] < CH["max_ticks"]:
        before = c["t"]
        chain_ticks(c, 1)
        if c["t"] == before:
            break
    return c


def averages(lengths):
    if not lengths:
        return 0.0, 0.0, 0.0
    n, s1, s2 = len(lengths), sum(lengths), sum(L * L for L in lengths)
    xn, xw = s1 / n, s2 / s1
    return xn, xw, xw / xn


def step_dist_df(s, label, xmax=15):
    L = [m[0] for m in s["mols"]]
    n = len(L)
    return pd.DataFrame({"x": list(range(1, xmax + 1)),
                         "fraction": [sum(1 for v in L if v == x) / n for x in range(1, xmax + 1)],
                         "run": label})


def chain_dist_df(c, label, width=50, xmax=600):
    P = c["dead"] + c["active"]
    edges = list(range(0, xmax, width))
    n = max(1, len(P))
    return pd.DataFrame({"x": [e + width / 2 for e in edges],
                         "fraction": [sum(1 for v in P if e < v <= e + width) / n for e in edges],
                         "run": label})


def run_sim():
    st.subheader("Mini simulator: watch the pot evolve")
    st.markdown("Every run uses its own random seed. Two runs stopped at the **same** p or x give "
                "**different** histograms (random fluctuations), while the *averages* follow the theory. "
                "Use the replicate panel below to see this directly.")
    left, right = st.columns(2)

    # ---------------- step growth: single run ----------------
    with left:
        st.markdown(f"#### Step growth (A–A + B–B, {N_STEP} + {N_STEP} molecules)")
        if "sim_s" not in ss:
            ss.sim_s = step_new(new_seed())
        b1, b2 = st.columns(2)
        if b1.button("Form 20 bonds"):
            step_bonds(ss.sim_s, 20)
        if b2.button("New random run", key="rs1"):
            ss.sim_s = step_new(new_seed())
        s = ss.sim_s
        p = s["bonds"] / s["A0"]
        L = [m[0] for m in s["mols"]]
        xn, xw, D = averages(L)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Extent p", f"{p:.2f}")
        m2.metric("Xₙ (= 1/(1−p))", f"{xn:.2f}")
        m3.metric("Đ sim", f"{D:.2f}")
        m4.metric("Đ theory 1+p", f"{1 + p:.2f}")
        xmax = min(max(L), 30)
        df = step_dist_df(s, "this run", xmax)
        theo = pd.DataFrame({"x": list(range(1, xmax + 1)),
                             "fraction": [(1 - p) * p ** (x - 1) for x in range(1, xmax + 1)]})
        bars = alt.Chart(df).mark_bar(color="#2563eb", opacity=0.75).encode(
            x=alt.X("x:Q", title="Chain length x (units)", scale=alt.Scale(domain=[0.5, xmax + 0.5])),
            y=alt.Y("fraction:Q", title="Number fraction"))
        line = alt.Chart(theo).mark_line(color="#0f172a", strokeDash=[5, 4], point=True).encode(x="x:Q", y="fraction:Q")
        st.altair_chart(bars + line if p > 0 else bars, width="stretch")
        st.caption(f"Seed {s['seed']}. Bars: this run. Dashed: Flory most-probable distribution (1 − p)·p^(x−1). "
                   "Xₙ always equals 1/(1 − p) exactly, because each bond removes exactly one molecule "
                   "(Xₙ = N₀/Nₜ); the *shape* of the distribution is what changes from run to run.")

    # ---------------- chain growth: single run ----------------
    with right:
        st.markdown(f"#### Chain growth ({CH['M0']} styrene, {CH['I0']} AIBN)")
        if "sim_c" not in ss:
            ss.sim_c = chain_new(new_seed())
        b1, b2 = st.columns(2)
        if b1.button("Run 5 time steps"):
            chain_ticks(ss.sim_c, 5)
        if b2.button("New random run", key="rs2"):
            ss.sim_c = chain_new(new_seed())
        c = ss.sim_c
        P = c["dead"] + c["active"]
        xn, xw, D = averages(P)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Conversion x", f"{chain_conv(c):.2f}")
        m2.metric("Xₙ of polymer", f"{xn:.0f}")
        m3.metric("Đ sim", f"{D:.2f}" if P else "–")
        m4.metric("Active radicals", len(c["active"]))
        if P:
            df = chain_dist_df(c, "this run")
            st.altair_chart(alt.Chart(df).mark_bar(color="#16a34a", opacity=0.8).encode(
                x=alt.X("x:Q", title="Chain length (units, bins of 50)"),
                y=alt.Y("fraction:Q", title="Number fraction of chains")), width="stretch")
        else:
            st.info("No chains yet: press 'Run 5 time steps'.")
        st.caption(f"Seed {c['seed']}. Monomer left: {c['M']} of {CH['M0']}; initiator left: {c['I']}. "
                   "Long chains appear immediately while monomer persists. Termination by combination "
                   "gives Đ ≈ 1.5 in theory." + (" Initiator exhausted: 'dead-end' polymerisation."
                                                 if c["I"] == 0 and not c["active"] else ""))

    # ---------------- replicate experiment ----------------
    st.divider()
    st.subheader("Replicate experiment: same conversion, different random runs")
    st.markdown("Stop several independent runs at the **same** conversion and compare. "
                "Scatter between runs is the stochastic nature of polymerisation; the theory curve is the average.")
    n_rep = st.slider("Number of replicate runs", 3, 8, 5)
    r1, r2 = st.columns(2)
    with r1:
        p_t = st.slider("Step growth: stop at p =", 0.30, 0.90, 0.70, 0.05)
        if st.button("Run step-growth replicates"):
            ss.rep_s = (p_t, [step_run_to(new_seed(), p_t) for _ in range(n_rep)])
        if "rep_s" in ss:
            p_r, runs = ss.rep_s
            frames = [step_dist_df(s, f"run {i + 1}") for i, s in enumerate(runs)]
            theo = pd.DataFrame({"x": list(range(1, 16)),
                                 "fraction": [(1 - p_r) * p_r ** (x - 1) for x in range(1, 16)],
                                 "run": "theory"})
            dfr = pd.concat(frames + [theo])
            st.altair_chart(alt.Chart(dfr).mark_line(point=True).encode(
                x=alt.X("x:Q", title="Chain length x"), y=alt.Y("fraction:Q", title="Number fraction"),
                color=alt.Color("run:N", title=None, scale=alt.Scale(
                    domain=[f"run {i + 1}" for i in range(len(runs))] + ["theory"],
                    range=["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c",
                           "#0891b2", "#ca8a04", "#db2777"][:len(runs)] + ["#0f172a"])),
                strokeDash=alt.condition(alt.datum.run == "theory", alt.value([6, 4]), alt.value([1, 0])),
                strokeWidth=alt.condition(alt.datum.run == "theory", alt.value(3), alt.value(1.5))),
                width="stretch")
            rows = []
            for i, s in enumerate(runs):
                xn, xw, D = averages([m[0] for m in s["mols"]])
                rows.append({"run": i + 1, "seed": s["seed"], "Xn": round(xn, 2), "Xw": round(xw, 2),
                             "Đ": round(D, 2), "longest chain": max(m[0] for m in s["mols"])})
            rows.append({"run": "theory", "seed": "", "Xn": round(1 / (1 - p_r), 2),
                         "Xw": round((1 + p_r) / (1 - p_r), 2), "Đ": round(1 + p_r, 2), "longest chain": ""})
            st.dataframe(pd.DataFrame(rows).astype(str), hide_index=True, width="stretch")
            st.caption(f"All runs stopped at p = {p_r:.2f}. Xₙ is identical by definition; Xw, Đ and the longest "
                       "chain scatter. With only 200 molecules the scatter is large; a real flask has ~10²³.")
    with r2:
        x_t = st.slider("Chain growth: stop at x =", 0.10, 0.80, 0.40, 0.05)
        if st.button("Run chain-growth replicates"):
            ss.rep_c = (x_t, [chain_run_to(new_seed(), x_t) for _ in range(n_rep)])
        if "rep_c" in ss:
            x_r, runs = ss.rep_c
            dfr = pd.concat([chain_dist_df(c, f"run {i + 1}") for i, c in enumerate(runs)])
            st.altair_chart(alt.Chart(dfr).mark_line(point=True).encode(
                x=alt.X("x:Q", title="Chain length (bins of 50)"), y=alt.Y("fraction:Q", title="Number fraction"),
                color=alt.Color("run:N", title=None)), width="stretch")
            rows = []
            for i, c in enumerate(runs):
                P = c["dead"] + c["active"]
                xn, xw, D = averages(P)
                rows.append({"run": i + 1, "seed": c["seed"], "x reached": round(chain_conv(c), 3),
                             "chains": len(P), "Xn": round(xn), "Đ": round(D, 2), "time steps": c["t"]})
            st.dataframe(pd.DataFrame(rows).astype(str), hide_index=True, width="stretch")
            st.caption(f"All runs stopped at x ≈ {x_r:.2f}. Chain count, Xₙ and Đ scatter between runs; "
                       "Xₙ is set by the kinetic chain length, not by conversion. Đ scatters around 1.5–1.8 (ideal combination gives 1.5; "
                       "the falling [M] and random lifetimes in this toy model broaden it), "
                       "(combination), unlike step growth where Đ → 2.")

    with st.expander("Reproduce a specific run from its seed"):
        cc1, cc2, cc3 = st.columns(3)
        seed_in = cc1.number_input("Seed", 1, 10**6, 12345)
        which = cc2.selectbox("Simulator", ["Step growth", "Chain growth"])
        if cc3.button("Load this seed"):
            if which == "Step growth":
                ss.sim_s = step_new(int(seed_in))
            else:
                ss.sim_c = chain_new(int(seed_in))
            st.rerun()
        st.caption("The same seed and the same button presses always reproduce the same run.")
    st.caption("Toy stochastic models for intuition only: rates and numbers are illustrative, not fitted to real kinetics.")


# =============================================================================
# 7. Layout
# =============================================================================
st.title("Step vs Chain Growth Lab")
st.caption("Predict first, then reveal. Focus on **which molecules are allowed to react** at each stage.")

with st.sidebar:
    st.header("Progress")
    for k, name in ROUTE_NAMES.items():
        res = ss.get(f"{k}_res", {})
        att = ss.get(f"{k}_attempt", 1)
        st.markdown(f"**{name}**  \nAttempt {att}: {sum(res.values())} / {len(res)} correct "
                    f"({len(res)}/{N_SLOTS} answered)")
        hist = ss.get(f"{k}_hist", {})
        if hist:
            st.caption("Finished attempts: " + ", ".join(f"#{a}: {v}/{N_SLOTS}" for a, v in sorted(hist.items())))
        seen = ss.get(f"{k}_seen", {})
        st.caption(f"Question bank explored: {len(seen)}/{len(BANKS[k])}")
    st.divider()
    st.markdown("**Bead key**")
    st.markdown("🔵 T = terephthaloyl · 🟠 E = glycol unit  \n"
                "🟢 S = styrene unit · St = monomer  \n"
                "🟣 I = initiator fragment · 🔴 • = radical")
    with st.expander("Model limitations"):
        st.markdown("- Beads are schematic: no bond angles or 3D structure.\n"
                    "- PET shown via direct esterification of TPA, with the melt transesterification step in Round 4.\n"
                    "- Chain transfer, the gel effect and cyclisation are mentioned but not simulated.\n"
                    "- Simulators are toy Monte Carlo models.")

tabs = st.tabs(["1 · PET step growth", "2 · Styrene chain growth", "3 · Mystery challenge",
                "4 · Compare", "5 · Simulator"])
with tabs[0]:
    run_route("pet")
with tabs[1]:
    run_route("sty")
with tabs[2]:
    run_mystery()
with tabs[3]:
    run_compare()
with tabs[4]:
    run_sim()
