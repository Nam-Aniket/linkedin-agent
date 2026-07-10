#!/usr/bin/env python3
"""Integration: a story becomes a BESPOKE cover.

Ties the pieces together:
  story {hook, mood, copy}
    -> archetype template   (html_templates, by hook)
    -> generated palette    (palette_gen.palette_for, by mood + seed)
    -> differentiating element (element.element, by derived keywords)  <- injected into the slot
    -> HTML -> PNG          (render_html.render, Playwright/Chromium)

The element SVG is string-injected into the template's `.element-slot` (un-hiding it and
setting `color:var(--muted)` so it floats as a secondary mark and inherits the palette).
This keeps both agents' files untouched.

  python3 render_covers.py   # renders drafts/cover_*.png + bespoke_covers_contactsheet.png
"""
import hashlib
import re
from pathlib import Path

import html_templates
import element as element_mod
import design_score
from palette_gen import palette_for
from render_html import render

DRAFTS = Path(__file__).parent / "drafts"

# story hook shape -> html_templates template name
HOOK_TEMPLATE = {
    "stat": "number_hero", "statement": "statement", "versus": "versus",
    "contrast": "contrast", "list": "index", "multistat": "stat_grid",
    "question": "question", "definition": "definition",
}

_WORD = re.compile(r"[a-zA-Z0-9]+")
# every place a template's copy can carry a topic word
_TEXT_KEYS = ("eyebrow", "headline", "caption", "term", "sub", "left", "right", "subject")


def _topic(story):
    """Derive {hook, mood, subject, keywords} from a story so element() can pick a mark.
    (In production the composer tags subject/keywords directly; here we mine the copy.)"""
    text = " ".join(str(story.get(k, "")) for k in _TEXT_KEYS)
    for k in ("items", "stats"):
        v = story.get(k)
        if v:
            text += " " + " ".join(str(x) for row in v
                                   for x in (row if isinstance(row, (list, tuple)) else [row]))
    return {"hook": story["hook"], "mood": story["mood"],
            "subject": story.get("eyebrow", ""),
            "keywords": [w.lower() for w in _WORD.findall(text)]}


_SLOT = re.compile(r'<div class="element-slot" style="([^"]*)"></div>')

# seeded element PLACEMENTS - variety across posts, and the bottom ones fill the
# dead bottom third (the audit's + design_score's top-heavy weakness). "mr" exists for
# explicit use but is NOT in the seeded rotation: the middle band is where wide
# headlines and right-aligned heroes live (three collisions in one render proved it).
PLACEMENTS = {
    "tr": "top:0; right:0; width:260px; height:260px;",
    "mr": "top:38%; right:0; width:240px; height:240px;",
    "br": "bottom:130px; right:0; width:290px; height:290px;",
    "bl": "bottom:130px; left:0; width:260px; height:260px;",
    "tr-sm": "top:0; right:0; width:150px; height:150px;",  # last-rung: tall+wide layouts
}
ROTATION = ("tr", "br", "bl")


def _inject(html_str, svg, placement=None):
    """Fill + un-hide the element slot; placement (a PLACEMENTS key) overrides the
    template's default slot position so composition varies across posts. The wrapper is
    tagged data-lint so the browser collision lint SEES the element (an untagged element
    slid past the lint and collided with the hero - eyes caught it, now the gate does)."""
    sized = svg.replace("<svg ", '<svg style="height:62%;width:auto" ', 1)

    def repl(m):  # function form: no escape processing on the SVG body
        style = PLACEMENTS.get(placement, m.group(1))
        return ('<div class="element-slot" data-lint="text" style="position:absolute; ' + style +
                ' display:flex; align-items:center; justify-content:center; color:var(--muted);">'
                + sized + '</div>')
    return _SLOT.sub(repl, html_str, count=1)


def _story_seed(story):
    """Deterministic: the SAME story always gets the same palette variation."""
    key = story.get("subject") or story.get("eyebrow", "") + story.get("headline", "")
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % 7


def build(story, seed=None, placement=None):
    name = HOOK_TEMPLATE[story["hook"]]
    s = _story_seed(story) if seed is None else seed
    if placement is None:  # seeded variety: different stories get different slots
        placement = ROTATION[s % len(ROTATION)]
    pal = palette_for(story["mood"], s)
    el = element_mod.element(_topic(story))
    html_str = html_templates.TEMPLATES[name](pal, story)
    return _inject(html_str, el["svg"], placement), name, pal, el["kind"], placement


BALANCE_SOFT = 0.33   # soft target only - the recompose loop steers toward it; the HARD
                      # gate stays at design_score's calibrated thresholds (evidence rule)


def compose_best(story, out, max_tries=5):
    """Self-healing render: render -> score -> if hard-fail or top-heavy, recompose.
    Ladder: (1) as seeded, (2) move the element to the bottom (fills a dead bottom
    third, lifts balance_y), (3) jitter the palette seed. First attempt that clears the
    hard gate AND the soft balance target wins; else first that clears the hard gate;
    else the last render (reported). Returns (name, pal, kind, placement, m, fails, tries)."""
    s0 = _story_seed(story)
    seeded = ROTATION[s0 % len(ROTATION)]
    # try the seeded placement, then every OTHER placement, then a SMALL element
    # (tall+wide layouts where no full-size corner fits), then jitter the palette seed
    plan = ([(s0, seeded)] +
            [(s0, p) for p in ROTATION if p != seeded] +
            [(s0, "tr-sm"), (s0 + 3, "tr-sm")])[:max_tries]
    fallback = None
    for i, (seed, forced) in enumerate(plan, 1):
        html_str, name, pal, kind, placed = build(story, seed=seed, placement=forced)
        try:
            render(html_str, out, check=True)   # browser lint: clip/overlap incl. the element
            m, fails = design_score.score(out)
        except RuntimeError as e:               # collision -> counts as a fail, ladder advances
            # a lint fail on the FIRST rung means no PNG exists yet (the worker
            # lints before it screenshots) - scoring a missing file killed the
            # whole ladder instead of advancing it
            m = design_score.metrics(out) if Path(out).exists() else {"balance_y": 0.0}
            fails = [f"browser lint: {e}"]
        result = (name, pal, kind, placed, m, fails, i)
        if not fails and m["balance_y"] >= BALANCE_SOFT:
            return result                      # passes hard gate + soft balance: done
        if not fails and fallback is None:
            fallback = result                  # hard-clean but top-heavy: keep as fallback
    if fallback is not None:
        # re-render the fallback (a later attempt overwrote the PNG)
        html_str, name, pal, kind, placed = build(story, seed=plan[fallback[6] - 1][0],
                                                  placement=plan[fallback[6] - 1][1])
        render(html_str, out)
        return fallback
    return result                              # nothing clean: last attempt, fails reported


# PLACEHOLDER showcase - one story per hook shape, plus two that exercise the logo
# and motif element kinds. Illustrative demo copy only; real posts come from your
# own gated briefs, wearing your profile.json moods.
SHOWCASE = [
    {"hook": "stat", "mood": "urgency", "eyebrow": "the number", "number": "70%",
     "caption": "of demo pipelines die before the first real post", "subject": "demo stat"},
    {"hook": "statement", "mood": "bold", "eyebrow": "the take",
     "headline": "Bigger models are not the fix", "subject": "demo statement"},
    {"hook": "versus", "mood": "calm", "eyebrow": "pick one", "left": "SPEED",
     "right": "CRAFT", "sub": "you only get to maximize one", "subject": "demo versus"},
    {"hook": "contrast", "mood": "growth", "eyebrow": "before / after", "before": "9 s",
     "after": "0.6 s", "caption": "one index change cut our p95 latency",
     "subject": "demo contrast"},
    {"hook": "list", "mood": "neutral", "eyebrow": "in production",
     "headline": "5 prompts that break silently",
     "items": ["the empty retrieval", "the token overflow", "the silent truncation",
               "the locale mismatch", "the stale cache"], "subject": "demo list"},
    {"hook": "multistat", "mood": "urgency", "eyebrow": "one feature, fully loaded",
     "stats": [["$0.03", "per call"], ["4", "model hops"], ["900ms", "p95 latency"],
               ["12%", "cache hits"]], "subject": "demo multistat"},
    {"hook": "question", "mood": "calm", "eyebrow": "gut check",
     "headline": "Is your retrieval actually retrieving?", "subject": "demo question"},
    {"hook": "definition", "mood": "neutral", "eyebrow": "glossary", "term": "eval",
     "pron": "/ee-val/", "defs": ["a repeatable test that scores model output",
                                  "the thing you wish you had before shipping"],
     "subject": "demo definition"},
    {"hook": "statement", "mood": "bold", "eyebrow": "tool teardown",
     "headline": "GitHub Copilot is a very fast junior", "subject": "GitHub Copilot"},
    {"hook": "statement", "mood": "calm", "eyebrow": "a note on craft",
     "headline": "Taste is a skill you can build", "subject": "a quiet essay on craft"},
]


def main():
    DRAFTS.mkdir(exist_ok=True)
    items = []
    for i, st in enumerate(SHOWCASE):
        out = DRAFTS / f"cover_{i}_{HOOK_TEMPLATE[st['hook']]}.png"
        name, pal, kind, placed, m, fails, tries = compose_best(st, out)
        flag = "  !! " + "; ".join(fails) if fails else ""
        heal = f" (healed x{tries})" if tries > 1 else ""
        items.append((f"{st['eyebrow']}  ->  {name} + {kind} @{placed}", out))
        print(f"{st['eyebrow']:30s} -> {name:12s} {kind:5s} @{placed:2s} {pal['accent']} "
              f"bal={m['balance_y']} ws={m['whitespace']}{heal}{flag}")

    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    cols = 5
    rows = -(-len(items) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 5.3 * rows), facecolor="white")
    axes = axes.flatten()
    for ax in axes:
        ax.axis("off")
    for ax, (cap, path) in zip(axes.flat, items):
        ax.imshow(mpimg.imread(path))
        ax.set_title(cap, fontsize=9, color="#333")
    fig.suptitle("Bespoke covers: topic -> archetype + generated palette + differentiating element",
                 fontsize=13, color="#222", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = DRAFTS / "bespoke_covers_contactsheet.png"
    fig.savefig(out, dpi=95, facecolor="white")
    plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    main()
