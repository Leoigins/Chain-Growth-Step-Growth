"""
Step vs Chain Growth Lab
------------------------
An interactive Streamlit tool that lets undergraduates *predict* each step of
  (1) PET step-growth polymerisation (terephthalic acid + ethylene glycol), and
  (2) styrene free-radical chain-growth polymerisation (AIBN initiator),
then reveal an animated schematic + explanation. A final "mystery" challenge
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
}
LBL = {"T": "T", "E": "E", "S": "S", "M": "St", "I": "I",
       "G1": "", "G2": "", "G3": ""}
TXT = {"M": "#14532d"}

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
        s_a, _ = species_svg(a, (W - wa) / 2, y)
        s1, _ = species_svg(p1, W / 2 - 16 - w1, y)
        s2, _ = species_svg(p2, W / 2 + 16, y)
        body.append(f'<g class="ra">{s_a}</g><g class="p1">{s1}</g><g class="p2">{s2}</g>')
        body.append(f'<circle class="flash" cx="{W / 2}" cy="{y}" r="20" fill="#fde047"/>')
        kf("ma", "0%{opacity:1}38%{opacity:1}48%{opacity:0}100%{opacity:0}")
        kf("mp1", "0%{opacity:0;transform:translateX(0)}45%{opacity:0;transform:translateX(0)}"
                  "55%{opacity:1}100%{opacity:1;transform:translateX(-150px)}")
        kf("mp2", "0%{opacity:0;transform:translateX(0)}45%{opacity:0;transform:translateX(0)}"
                  "55%{opacity:1}100%{opacity:1;transform:translateX(150px)}")
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
def step(units):
    """PET species: T = terephthaloyl, E = ethylene-glycol unit."""
    units = list(units)
    return {"units": units,
            "left": "HOOC" if units[0] == "T" else "HO",
            "right": "COOH" if units[-1] == "T" else "OH"}


TPA, EG = step("T"), step("E")
STY = {"units": ["M"], "tag": "CH₂=CH–Ph"}
AIBN = {"units": ["I", "I"], "link": "–N=N–", "tag": "AIBN"}
I_RAD = {"units": ["I"], "right": "•"}


def pchain(n, active=True, flip=False):
    """Polystyrene chain: initiator fragment + n styrene units (+ radical end)."""
    u = ["I"] + ["S"] * n
    if flip:
        return {"units": u[::-1], "left": "•" if active else ""}
    return {"units": u, "right": "•" if active else ""}


def dead(n):  # combination product: I-(S)n-I
    return {"units": ["I"] + ["S"] * n + ["I"]}


# =============================================================================
# 3. Round content
# =============================================================================
PET_ROUNDS = [
    dict(
        title="Round 1 · What starts the reaction?",
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
        explain=("**Esterification**: a COOH group reacts with an OH group, releasing water. "
                 "No initiator is needed; the functional groups themselves are the reactive sites. "
                 "Acid + acid cannot form an ester. *Nuance:* EG + EG can form a diethylene glycol "
                 "(ether) side product at ~1–2 %, which is a defect, not the chain-building step."),
        anims=[
            dict(kind="combine", reactants=[TPA, EG], product=step("TE"), byproduct="H₂O",
                 caption="COOH + HO → ester. The dimer still has one COOH and one OH end, so it can keep reacting."),
            dict(kind="bounce", allowed=False, reactants=[TPA, TPA],
                 caption="COOH + COOH: no complementary partner, so no ester forms."),
        ]),
    dict(
        title="Round 2 · Who can react with whom?",
        context="A few minutes later the pot holds monomers **and** a new dimer HOOC–T–E–OH.",
        pot=[(TPA, 3), (EG, 3), (step("TE"), 3)],
        type="multi",
        question="Select **every** pair that can form a new ester link.",
        options=["Dimer + EG", "Dimer + TPA", "Dimer + Dimer", "TPA + EG",
                 "TPA + TPA", "EG + EG (backbone ester)"],
        answer={0, 1, 2, 3},
        explain=("**Any** molecule with a COOH end can react with **any** molecule with an OH end, "
                 "whatever its size. Flory's *equal-reactivity principle*: the reactivity of an end group "
                 "is essentially independent of chain length. There is no special 'active centre'. "
                 "This is the defining feature of **step growth**."),
        anims=[
            dict(kind="combine", reactants=[step("TE"), step("TE")], product=step("TETE"), byproduct="H₂O",
                 caption="Oligomer + oligomer: two dimers couple into a tetramer in one step."),
            dict(kind="combine", reactants=[step("TE"), EG], product=step("ETE"), byproduct="H₂O",
                 caption="Dimer + monomer works just as well: the COOH end meets EG."),
        ]),
    dict(
        title="Round 3 · How long are the chains halfway through?",
        context=("Half of all COOH groups have now reacted (extent of reaction **p = 0.50**). "
                 "Almost no free monomer remains, but look at the chain lengths."),
        pot=[(TPA, 1), (EG, 1), (step("TE"), 3), (step("ETE"), 2), (step("TET"), 2), (step("TETE"), 1)],
        type="single",
        question="What is the number-average degree of polymerisation, Xₙ?",
        options=["Xₙ = 2", "Xₙ ≈ 50", "Xₙ ≈ 100", "Xₙ ≈ 1.5"],
        answer=0,
        explain=("**Carothers equation**: Xₙ = 1 / (1 − p) = 1 / 0.5 = **2**. "
                 "Monomer is used up early, yet the chains are still short. Long chains only appear "
                 "at the very end, when oligomers join together. p = 0.90 gives Xₙ = 10; p = 0.99 gives Xₙ = 100."),
        anims=[
            dict(kind="combine", reactants=[step("TETE"), step("TETE")], product=step("TETETETE"),
                 byproduct="H₂O", caption="Late-stage growth: chain length doubles when two oligomers join."),
        ]),
    dict(
        title="Round 4 · Making bottle-grade PET",
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
        explain=("Esterification and transesterification are **equilibria**, so the small molecule must be "
                 "removed (Le Chatelier) to push p → 1. High conversion is essential (Carothers), and any "
                 "imbalance of functional groups caps the chain ends (see next round). There is no initiator "
                 "in step growth. Cooling would freeze the melt and stop diffusion, not help growth. "
                 "In the melt stage, a glycol OH end attacks an ester near another chain end and **releases EG**."),
        anims=[
            dict(kind="combine", reactants=[step("ETE"), step("ETE")], product=step("ETETE"),
                 byproduct="HOCH₂CH₂OH ↑ (vacuum)",
                 caption="Transesterification: two glycol-ended chains join and expel ethylene glycol, which is pumped away."),
        ]),
    dict(
        title="Round 5 · The cost of imbalance",
        context="Suppose you weigh out a **1 mol % excess of EG**, so the ratio of groups is r = 0.99.",
        pot=[(TPA, 5), (EG, 5)],
        type="single",
        question="Even if every COOH reacts (p = 1), what is the maximum Xₙ?",
        options=["Xₙ ≈ 199", "Xₙ → ∞", "Xₙ ≈ 100", "Xₙ ≈ 99"],
        answer=0,
        explain=("Modified Carothers: Xₙ = (1 + r) / (1 + r − 2rp). At p = 1: Xₙ = (1 + r)/(1 − r) = 1.99/0.01 "
                 "= **199**. Once all the COOH is consumed, every chain has OH at both ends and **no complementary "
                 "partner is left**. This is why stoichiometry (or controlled removal of excess EG) matters so much "
                 "in step growth, while it is irrelevant in chain growth."),
        anims=[
            dict(kind="bounce", allowed=False, reactants=[step("ETETE"), step("ETE")],
                 caption="OH end + OH end: both chains are 'capped' by the excess glycol, so growth stops."),
        ]),
]

STY_ROUNDS = [
    dict(
        title="Round 1 · What starts the reaction?",
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
        explain=("**Initiation part 1**: the weak C–N bonds of AIBN break homolytically (half-life ~10 h at 65 °C) "
                 "to give two 2-cyano-2-propyl radicals and N₂ gas. Only a fraction *f* ≈ 0.5–0.7 of these "
                 "radicals escape the solvent cage to start chains. Styrene monomers cannot link to each other "
                 "without a reactive centre. *Nuance:* above ~100 °C styrene can self-initiate thermally, "
                 "but at 70 °C with AIBN the initiator dominates."),
        anims=[
            dict(kind="split", reactants=[AIBN], products=[I_RAD, I_RAD], byproduct="N₂ ↑",
                 caption="Homolysis gives two primary radicals, the only species that can start chains."),
            dict(kind="bounce", allowed=False, reactants=[STY, STY],
                 caption="Monomer + monomer: no radical, no reaction."),
        ]),
    dict(
        title="Round 2 · Where does the radical add?",
        context="An initiator radical R• meets a styrene molecule CH₂=CH–Ph.",
        pot=[(I_RAD, 1), (STY, 8)],
        type="single",
        question="Which carbon does R• attack, and why?",
        options=["The CH₂ carbon, giving a benzylic radical stabilised by the phenyl ring",
                 "The CH(Ph) carbon, giving a primary radical on CH₂",
                 "The phenyl ring, removing aromaticity",
                 "Neither: R• abstracts H to form an ester"],
        answer=0,
        explain=("Addition to the unsubstituted CH₂ end gives **R–CH₂–C•H–Ph**, a benzylic radical "
                 "delocalised into the ring. This regioselectivity makes the polymer **head-to-tail**. "
                 "The product is still a radical: the active centre has **moved** to the chain end."),
        anims=[
            dict(kind="combine", reactants=[I_RAD, STY], product=pchain(1), caption=
                 "Initiation part 2: R• + CH₂=CHPh → R–CH₂–CH(Ph)•. The radical is carried at the new chain end."),
        ]),
    dict(
        title="Round 3 · Who can react with whom?",
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
                 "each other. Compare with PET, where *every* molecule is reactive. "
                 "*Nuance:* a radical can occasionally abstract H from a dead chain (chain transfer to polymer), "
                 "but this is minor for styrene."),
        anims=[
            dict(kind="combine", reactants=[pchain(4), STY], product=pchain(5),
                 caption="Propagation: monomer adds one at a time; the radical stays at the chain end."),
            dict(kind="bounce", allowed=False, reactants=[dead(4), STY],
                 caption="Dead chain + monomer: no active centre, so no reaction."),
            dict(kind="bounce", allowed=False, reactants=[STY, STY],
                 caption="Monomer + monomer: still no reaction without a radical."),
        ]),
    dict(
        title="Round 4 · A snapshot at 10 % conversion",
        context="Only 10 % of the styrene has been consumed.",
        pot=[(STY, 18), (dead(14), 1), (pchain(9), 1)],
        type="single",
        question="What does the reactor contain?",
        options=["Mostly monomer, some already-long chains, and a tiny concentration of radicals",
                 "All chains are short oligomers (Xₙ ≈ 1.1)",
                 "No polymer yet: polymer only forms near 100 % conversion",
                 "Mainly dimers and trimers"],
        answer=0,
        explain=("Radical concentration is only ~10⁻⁸ mol L⁻¹, but propagation is fast (k_p ≈ 340 L mol⁻¹ s⁻¹ "
                 "at 60 °C), so each chain grows to **full length within about a second**, then dies. "
                 "High-molar-mass polymer is present **from the start**; conversion rises by forming *more* "
                 "chains, not by making existing chains longer. This is the exact opposite of Round 3 in the PET route."),
        anims=[
            dict(kind="combine", reactants=[pchain(9), STY], product=pchain(10),
                 caption="Each active chain adds thousands of monomers in its short lifetime."),
        ]),
    dict(
        title="Round 5 · How does a chain die?",
        context="Two growing polystyryl radicals meet.",
        pot=[(pchain(6), 1), (pchain(5, flip=True), 1), (STY, 6)],
        type="single",
        question="What happens **predominantly** for styrene?",
        options=["Combination: the radicals pair up into one dead chain (head-to-head link)",
                 "Disproportionation dominates, giving two dead chains",
                 "They keep growing as one chain with two radical ends",
                 "They form an ester and release water"],
        answer=0,
        explain=("For polystyrene, termination is **mainly by combination**: the two radical ends form a C–C bond, "
                 "leaving one dead chain with a head-to-head junction, so Xₙ ≈ 2ν (ν = kinetic chain length). "
                 "Disproportionation (H-transfer giving one saturated and one unsaturated end) dominates for "
                 "methacrylates such as PMMA. Termination is irreversible: dead chains never restart. "
                 "(Contrast: PET chain ends stay reactive.)"),
        anims=[
            dict(kind="combine", reactants=[pchain(6), pchain(5, flip=True)], product=dead(11),
                 caption="Combination: two active centres are destroyed, one long dead chain is formed."),
        ]),
]

ROUTES = {"pet": ("PET: step growth", PET_ROUNDS),
          "sty": ("Polystyrene: radical chain growth", STY_ROUNDS)}


# =============================================================================
# 4. Round engine
# =============================================================================
ss = st.session_state
ss.setdefault("nonce", 0)


def run_route(key):
    name, rounds = ROUTES[key]
    idx = ss.setdefault(f"{key}_idx", 0)
    results = ss.setdefault(f"{key}_res", {})

    if idx >= len(rounds):
        n_ok = sum(results.values())
        st.success(f"Route complete: **{n_ok} / {len(rounds)}** predictions correct.")
        st.markdown("Now try the **Mystery challenge** tab to test whether you can tell the two mechanisms apart "
                    "without labels.")
        if st.button("Restart this route", key=f"{key}_restart"):
            ss[f"{key}_idx"] = 0
            ss[f"{key}_res"] = {}
            for k in [k for k in ss.keys() if k.startswith(f"{key}_q") or k.startswith(f"{key}_why")]:
                del ss[k]
            st.rerun()
        return

    R = rounds[idx]
    st.progress(idx / len(rounds), text=f"{name} · round {idx + 1} of {len(rounds)}")
    st.subheader(R["title"])
    st.markdown(R["context"])
    svg, h = pot_svg(R["pot"], title="Reactor contents")
    components.html(BASE_CSS + svg, height=h + 16)

    answered = idx in results
    qkey = f"{key}_q{idx}"
    if R["type"] == "single":
        choice = st.radio(R["question"], R["options"], index=None, key=qkey, disabled=answered)
    else:
        choice = st.multiselect(R["question"], R["options"], key=qkey, disabled=answered)
    st.text_input("Your reasoning in one sentence (write it before you reveal):",
                  key=f"{key}_why{idx}", disabled=answered)

    if not answered:
        if st.button("Lock in my prediction", type="primary", key=f"{key}_lock{idx}"):
            if not choice:
                st.warning("Make a prediction first.")
            else:
                if R["type"] == "single":
                    ok = R["options"].index(choice) == R["answer"]
                else:
                    ok = {R["options"].index(c) for c in choice} == R["answer"]
                results[idx] = ok
                st.rerun()
        return

    # ---- reveal ----
    if results[idx]:
        st.success("Correct prediction.")
    else:
        st.error("Not quite. Compare your answer with the mechanism below.")
    if R["type"] == "multi":
        chosen = {R["options"].index(c) for c in (choice or [])}
        rows = []
        for i, opt in enumerate(R["options"]):
            truth = i in R["answer"]
            rows.append({"Pair / reaction": opt,
                         "Can react?": "Yes" if truth else "No",
                         "You said": "Yes" if i in chosen else "No",
                         "": "✓" if (i in chosen) == truth else "✗"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.markdown(f"**Answer:** {R['options'][R['answer']]}")
    st.info(R["explain"])

    st.markdown("**Animated schematic**")
    for a in R["anims"]:
        components.html(anim_html(a, ss.nonce), height=215)
    c1, c2 = st.columns([1, 4])
    if c1.button("Replay animations", key=f"{key}_replay{idx}"):
        ss.nonce += 1
        st.rerun()
    if c2.button("Next round →", type="primary", key=f"{key}_next{idx}"):
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


def sim_step_init(n=100):
    ss.sim_s = [[1, "A", "A"] for _ in range(n)] + [[1, "B", "B"] for _ in range(n)]
    ss.sim_s_bonds, ss.sim_s_A0 = 0, 2 * n


def sim_step_advance(k):
    mols = ss.sim_s
    for _ in range(k):
        Aend = [(i, s) for i, m in enumerate(mols) for s in (1, 2) if m[s] == "A"]
        Bend = [(i, s) for i, m in enumerate(mols) for s in (1, 2) if m[s] == "B"]
        for _try in range(20):
            if not Aend or not Bend:
                return
            (ia, sa), (ib, sb) = random.choice(Aend), random.choice(Bend)
            if ia != ib:
                break
        else:
            return
        ma, mb = mols[ia], mols[ib]
        new = [ma[0] + mb[0], ma[3 - sa], mb[3 - sb]]
        for i in sorted((ia, ib), reverse=True):
            mols.pop(i)
        mols.append(new)
        ss.sim_s_bonds += 1


def sim_chain_init():
    ss.sim_c = dict(M=5000, M0=5000, I=12, active=[], dead=[], t=0)


def sim_chain_advance(ticks):
    c = ss.sim_c
    for _ in range(ticks):
        c["t"] += 1
        for _ in range(c["I"]):
            if random.random() < 0.03:
                c["I"] -= 1
                c["active"] += [0, 0]
        grow = []
        for L in c["active"]:
            add = min(c["M"], max(0, round(random.gauss(12 * c["M"] / c["M0"], 2))))
            c["M"] -= add
            grow.append(L + add)
        random.shuffle(grow)
        keep = []
        while grow:
            L = grow.pop()
            if grow and random.random() < 0.12:
                c["dead"].append(L + grow.pop())
            else:
                keep.append(L)
        c["active"] = keep


def run_sim():
    st.subheader("Mini simulator: watch the pot evolve")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Step growth (A–A + B–B, 100 + 100 molecules)")
        if "sim_s" not in ss:
            sim_step_init()
        b1, b2 = st.columns(2)
        if b1.button("Form 20 bonds"):
            sim_step_advance(20)
        if b2.button("Reset", key="rs1"):
            sim_step_init()
        mols = ss.sim_s
        p = ss.sim_s_bonds / ss.sim_s_A0
        xn = sum(m[0] for m in mols) / len(mols)
        m1, m2, m3 = st.columns(3)
        m1.metric("Extent p", f"{p:.2f}")
        m2.metric("Xₙ (sim)", f"{xn:.1f}")
        m3.metric("Xₙ Carothers", f"{1 / (1 - p):.1f}" if p < 1 else "∞")
        df = pd.DataFrame({"length": [m[0] for m in mols]})
        st.altair_chart(alt.Chart(df).mark_bar(color="#2563eb").encode(
            x=alt.X("length:Q", bin=alt.Bin(maxbins=30), title="Chain length (units)"),
            y=alt.Y("count()", title="Number of molecules")), width="stretch")
        st.caption(f"Monomers left: {sum(1 for m in mols if m[0] == 1)} of 200. Note how monomer vanishes early.")
    with right:
        st.markdown("#### Chain growth (5000 styrene, 12 AIBN)")
        if "sim_c" not in ss:
            sim_chain_init()
        b1, b2 = st.columns(2)
        if b1.button("Run 5 time steps"):
            sim_chain_advance(5)
        if b2.button("Reset", key="rs2"):
            sim_chain_init()
        c = ss.sim_c
        conv = 1 - c["M"] / c["M0"]
        polys = c["dead"] + c["active"]
        xn = (sum(polys) / len(polys)) if polys else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Conversion x", f"{conv:.2f}")
        m2.metric("Xₙ of polymer", f"{xn:.0f}")
        m3.metric("Active radicals", len(c["active"]))
        if polys:
            df = pd.DataFrame({"length": polys})
            st.altair_chart(alt.Chart(df).mark_bar(color="#16a34a").encode(
                x=alt.X("length:Q", bin=alt.Bin(maxbins=30), title="Chain length (units)"),
                y=alt.Y("count()", title="Number of chains")), width="stretch")
        else:
            st.info("No chains yet: press 'Run 5 time steps'.")
        st.caption(f"Monomers left: {c['M']} of {c['M0']}. Long chains appear immediately while monomer persists.")
    st.caption("Toy stochastic models for intuition only: rates and numbers are illustrative, not fitted to real kinetics.")


# =============================================================================
# 7. Layout
# =============================================================================
st.title("Step vs Chain Growth Lab")
st.caption("Predict first, then reveal. Focus on **which molecules are allowed to react** at each stage.")

with st.sidebar:
    st.header("Progress")
    for k, (name, rounds) in ROUTES.items():
        res = ss.get(f"{k}_res", {})
        st.markdown(f"**{name}**: {sum(res.values())} / {len(res)} correct "
                    f"({len(res)}/{len(rounds)} answered)")
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
