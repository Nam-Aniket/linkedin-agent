#!/usr/bin/env python3
"""Mechanical quality gate for a LinkedIn draft — objective rules only.
Subjective judgment (hook strength, is there a real specific from YOUR work)
stays with the human/LLM reviewer; this just catches the auto-rejectable stuff.

Extend the word lists without editing code: profile.json voice.banned_extra
(list) and voice.jargon_extra (word -> plainer twin) are merged in below.

  python3 check.py --text-file draft.txt   # exit 0 = pass, 1 = fail
  python3 check.py --selftest
"""
import re, sys, argparse
from pathlib import Path

import config as _profile

# AI-tell phrases everyone should ban, + your additions from profile.json.
BANNED = [
    "leverage", "unlock", "supercharge", "game-changer", "game changer", "delve",
    "robust", "seamless", "at scale", "i came across", "i wanted to reach out",
    "elevate", "empower", "revolutionize", "in today's fast-paced", "tapestry",
    "testament to", "dive in", "navigate the", "in the realm of", "ever-evolving",
    "utilize", "utilise", "synergy", "holistic", "myriad", "plethora",
] + [str(w).lower() for w in _profile.P["voice"]["banned_extra"]]

# Plain-language gate: name the real thing in concrete words.
# "the gap between the cheapest and priciest task" beats "hides a 100x spread".
# These abstract/jargon words almost always have a plainer twin; each is flagged
# WITH the suggestion, so the author swaps it (or, if a term is genuinely essential,
# defines it in plain words on the slide - the Feynman rule, not a bare ban).
JARGON = {
    "spread": "gap", "inference": "running the model (or just 'AI')",
    "delta": "gap / change", "variance": "how much it varies",
    "throughput": "speed", "latency": "delay", "granular": "detailed",
    "methodology": "method", "paradigm": "model / way", "streamline": "simplify",
    "facilitate": "help / run", "optimize": "improve", "optimise": "improve",
    "utilization": "usage", "ecosystem": "the tools around it",
    **{str(k).lower(): str(v) for k, v in _profile.P["voice"]["jargon_extra"].items()},
}

# AI-rhythm detectors, born from a real miss (2026-07-08: the openwiki draft
# shipped "reads your repo, writes a wiki, and keeps it fresh" + "the clever
# part is..."). The voice rules always banned these; this makes the ban
# mechanical instead of relying on a human eye.
# Tricolon: three parallel items as "X, Y(,) and Z" inside one sentence.
# Items capped at 40 chars and may not contain :;- clause markers - real rhythm
# triads are short and punchy; a long subordinate clause followed by ", or X"
# is a CHOICE QUESTION, not a triad (false positive found on first real use).
_TRICOLON = re.compile(
    r"[^.!?\n,:;-]{3,40},\s+[^.!?\n,:;-]{3,40},?\s+(?:and|or)\s+[^.!?\n]{3,60}")
# Formulaic reveal: teases that something is interesting instead of saying it.
REVEAL_PHRASES = [
    "the clever part", "the best part", "the interesting part", "the crazy part",
    "the wild part", "the kicker", "here's the thing", "here is the thing",
    "plot twist", "the secret sauce", "let that sink in",
]


def ai_tells(text):
    """Rhythm/formula AI tells. Returns violations (hard fails - the voice
    rules ban these outright, same as em dashes)."""
    out = []
    low = text.lower()
    for p in REVEAL_PHRASES:
        if p in low:
            out.append(f"formulaic reveal '{p}' - say the interesting fact instead of teasing it")
    if _TRICOLON.search(text):
        out.append("tricolon (X, Y, and Z) - AI rhythm tell; drop to two items or restructure")
    return out


HARD_MIN, HARD_MAX = 400, 3000   # ugcPosts commentary hard cap ~3000 chars
AIM_MIN, AIM_MAX = 800, 1500     # target window (unverified, to A/B test)
CAR_MIN, CAR_AIM_MIN, CAR_AIM_MAX = 60, 100, 300  # carousel: short hook over the slides (unverified)

# The fold: LinkedIn truncates ~140 chars on mobile, ~210 on desktop, and a
# blank line ends the preview early. The hook must live inside the mobile budget.
FOLD_MOBILE, FOLD_DESKTOP = 140, 210
WEAK_OPENERS = ("so ", "today ", "in this post", "here is a", "here are a",
                "i wanted to", "i've been thinking", "as a ", "lately i",
                "recently i", "i'm excited", "i am excited", "let me tell")


def fold_snippet(text, limit):
    """What LinkedIn shows before 'see more': cut at limit or first blank line."""
    para_end = text.find("\n\n")
    cut = limit if para_end < 0 else min(limit, para_end)
    return text[:cut].replace("\n", " ").strip()


def hook_review(text):
    """Heuristic hook warnings + the mobile/desktop preview. Judgment stays human."""
    warns = []
    mobile = fold_snippet(text, FOLD_MOBILE)
    desktop = fold_snippet(text, FOLD_DESKTOP)
    stripped = text.lstrip()
    if any(stripped.lower().startswith(o) for o in WEAK_OPENERS):
        warns.append(f"weak opener '{stripped[:16]}...' — lead with the specific or the tension, not warm-up")
    if not re.search(r"\d", mobile):
        warns.append("no number in the mobile hook (~140 chars) — a specific number stops the scroll")
    first_para = text.split("\n\n", 1)[0]
    if "\n\n" in text and len(first_para) < 70:
        warns.append(f"hook paragraph is only {len(first_para)} chars before a break — that's all mobile shows")
    return warns, mobile, desktop


_CAPS_RUN = re.compile(r"\b[A-Z]{2,}(?:[\s,]+[A-Z]{2,}){3,}\b")


def caps_check(text):
    """No all-caps runs longer than 3 words (outside short eyebrow labels): caps flatten
    the word shapes readers recognize (Bouma), so long caps runs read slower. Acronyms
    and short label bursts pass. Returns violations."""
    return [f"all-caps run: '{m.group(0)[:40]}' - sentence case for anything longer than a label"
            for m in _CAPS_RUN.finditer(text)]


def plain_language(text):
    """Plainness lint: abstract/jargon words (with a plainer suggestion) + over-long
    sentences. Returns a list of violation strings. Used as ADVISORY warnings on post
    commentary (prose has latitude) and as a HARD gate on carousel slide copy (a slide
    is tiny and high-stakes, so it must be plain). Judgment still stays human."""
    out = []
    low = text.lower()
    for w, alt in JARGON.items():
        if re.search(rf"\b{re.escape(w)}\b", low):
            out.append(f"jargon '{w}' -> say it plainer: {alt}")
    for sent in re.split(r"[.!?]+", text):
        n = len(sent.split())
        if n > 16:
            out.append(f"long sentence ({n} words) -> break it up; a slide reads in one glance")
    return out


def check(text, carousel=False):
    """Return (fails, warnings). carousel=True relaxes the length window."""
    fails, warns = [], []
    low = text.lower()

    for p in BANNED:
        if p in low:
            fails.append(f"banned phrase: '{p}'")

    if "!" in text:
        fails.append("exclamation mark (voice rule: none)")

    urls = re.findall(r"https?://\S+|www\.\S+", text)
    if urls:
        fails.append(f"URL in body ({urls[0]}) — move to first comment (-18.8% reach)")

    if re.search(r"it['’]s not .{1,40}[,.] it['’]s", low):
        fails.append("'it's not X, it's Y' — flagged AI-slop construction")

    if "—" in text or "–" in text:
        fails.append("em or en dash present - use a plain hyphen (voice rule, and a classic AI tell)")

    lo, aim_lo, aim_hi = (CAR_MIN, CAR_AIM_MIN, CAR_AIM_MAX) if carousel else (HARD_MIN, AIM_MIN, AIM_MAX)
    n = len(text)
    if n < lo:
        fails.append(f"too short ({n} chars, min {lo})")
    elif n > HARD_MAX:
        fails.append(f"too long ({n} chars, LinkedIn caps ~{HARD_MAX})")
    elif not (aim_lo <= n <= aim_hi):
        warns.append(f"{n} chars (outside aim {aim_lo}-{aim_hi})")

    tags = re.findall(r"#\w+", text)
    if len(tags) > 5:
        fails.append(f"{len(tags)} hashtags (max ~5)")

    emojis = re.findall(r"[\U0001F000-\U0001FAFF☀-➿]", text)
    if len(emojis) > 6:
        warns.append(f"{len(emojis)} emojis (reads spammy)")

    spelled = re.findall(r"\b(twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion)\b", low)
    if spelled:
        warns.append(f"spelled-out number '{spelled[0]}' - a numeral scans better (no penalty for digits)")

    warns += [f"plain: {x}" for x in plain_language(text)]  # advisory on commentary
    fails += caps_check(text)                               # long caps runs: hard fail
    fails += ai_tells(text)                                 # tricolon/reveal: hard fail
    return fails, warns


def _selftest():
    f, _ = check("We leverage AI to unlock growth!")
    assert any("leverage" in x for x in f) and any("exclamation" in x for x in f), f
    f, _ = check("Check https://x.com now. " + "word " * 100)
    assert any("URL" in x for x in f), f
    f, _ = check("A clean sentence with an em dash — right here. " + "word " * 90)
    assert any("dash" in x for x in f), f
    _, w = check("We cut fifty steps down to three. " + "word " * 90)
    assert any("numeral" in x for x in w), w
    f, w = check("I shipped a caching fix that cut our token bill by 38 percent. "
                 "Here is the one line that did it and the trap it avoided. " + "detail " * 90)
    assert not f, f  # clean draft passes
    assert fold_snippet("Hello world.\n\nSecond para", 140) == "Hello world."  # blank line cuts early
    assert fold_snippet("x" * 300, 140) == "x" * 140                            # limit cuts
    hw, _, _ = hook_review("As a founder, I learned a lot. " + "word " * 100)
    assert any("weak opener" in x for x in hw), hw
    # plain-language gate: jargon phrasing must trip; the plain twin passes
    assert any("spread" in x for x in plain_language("this hides a 100x spread")), "jargon 'spread' should flag"
    assert plain_language("the gap between the cheapest and priciest task") == [], "plain copy must pass"
    assert any("inference" in x for x in plain_language("cutting inference cost")), "jargon 'inference' should flag"
    f2, _ = check("We utilize synergy to help. " + "word " * 100)
    assert any("utilize" in x for x in f2) and any("synergy" in x for x in f2), f2
    # caps gate: long shout fails, label-length caps and acronyms pass
    assert caps_check("THIS WHOLE HEADLINE IS SHOUTING AT YOU"), "long caps run should fail"
    assert caps_check("THE EVIDENCE") == [], "short label caps must pass"
    assert caps_check("our RAG and API bill for GPU time") == [], "acronyms must pass"
    # ai_tells: the two exact lines that slipped through on 2026-07-08 must fail
    assert any("tricolon" in x for x in ai_tells(
        "It reads your repo, writes a wiki, and keeps it fresh from CI.")), "tricolon must flag"
    assert any("reveal" in x for x in ai_tells(
        "The clever part is where it puts the output.")), "reveal phrase must flag"
    assert any("tricolon" in x for x in ai_tells(
        "We looked at pricing, usage patterns and retries.")), "no-oxford tricolon must flag"
    # ...and the human rewrite of the same post must pass clean
    assert ai_tells(
        "It reads your repo and writes a wiki for it. Then it keeps that wiki updated "
        "every time your code changes, straight from CI. It wires into AGENTS.md and "
        "CLAUDE.md, the files your coding agents already read for context.") == [], "rewrite must pass"
    assert ai_tells("a pause, and then it hit me") == [], "comma+and (two clauses) must pass"
    # choice questions are not triads (real false positives, 2026-07-08)
    assert ai_tells("When your AI bill jumped, what did you check first - the model "
                    "price, or the workload?") == [], "choice question must pass"
    assert ai_tells("When your AI bill last jumped, what did you check first: the "
                    "model price or the workload?") == [], "colon choice must pass"
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file")
    ap.add_argument("--text")
    ap.add_argument("--carousel", action="store_true",
                    help="relax the length window for a carousel's short commentary")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    text = a.text or Path(a.text_file).read_text()
    fails, warns = check(text, carousel=a.carousel)
    hwarns, mobile, desktop = hook_review(text)
    warns = warns + hwarns

    print("HOOK — what shows before 'see more':")
    print(f"  mobile ~140:  {mobile}")
    print(f"  desktop ~210: {desktop}\n")

    for w in warns:
        print(f"  warn: {w}")
    if fails:
        print("FAIL:")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    print(f"PASS ({len(text)} chars). Mechanical gate clear — subjective + hook review still required.")


if __name__ == "__main__":
    main()
