#!/usr/bin/env python3
"""Mechanical quality gate for the RESEARCH stage of the pipeline.

The research stage had no eval, so it kept shipping stale, unverified, or generic
picks. This lints a STRUCTURED research brief the same way check.py lints post text:
objective failures only. Judgment - is it newsworthy, on-brand, a real take - stays
with the human/LLM reviewer and RESEARCH.md.

A brief:
  {
    "topic": "...",
    "angle": "the specific take (not a generic roundup)",
    "items": [
      {"name": "OpenClaw",
       "claim": "personal AI assistant, runs locally",
       "metric": "382000 stars",
       "recency": "2026-01-30",                 # launch/last-relevant date, YYYY-MM or YYYY-MM-DD
       "primary_source": "https://github.com/openclaw/openclaw",
       "verified": "fetched repo 2026-07-06; 382k shown"},
    ],
  }

  python3 research_check.py --brief brief.json
  python3 research_check.py --selftest
"""
import argparse, json, sys
from pathlib import Path
from datetime import date

# Primary / authoritative hosts - a claim confirmed here is trustworthy.
PRIMARY_HOSTS = ("github.com", "gitlab.com", "wikipedia.org", "arxiv.org",
                 "huggingface.co", "docs.", ".dev/docs")
# Generic-roundup markers - the AI-slop framing LinkedIn suppresses.
SLOP_ANGLE = ("top 10", "top 5", "top ten", "best tools", "you should know",
              "must-have", "must have", "ultimate list", "tools you need",
              "you need to know", "game-chang")
# Big claims that need an authoritative source, not a blog.
SUPERLATIVE = ("most starred", "most popular", "fastest ever", "fastest-growing",
               "biggest", "first ever", "in history", "of all time", "record")
# Live velocity verdicts from gh_metrics.py - only "gaining now" trends clear the gate.
GOOD_TREND = ("RISING", "STEADY", "EXPLODING")

# Freshness knobs (unverified - tune against real engagement). A post is news.
STALE_MONTHS_WARN, STALE_MONTHS_FAIL = 6, 18


def _months_since(recency, as_of=None):
    """Months between an ISO date (YYYY-MM or YYYY-MM-DD) and as_of (default today).
    None if unparseable - unknown freshness is treated as a failure by the caller."""
    if not recency:
        return None
    as_of = as_of or date.today()
    parts = str(recency).split("-")
    try:
        y, m = int(parts[0]), (int(parts[1]) if len(parts) > 1 else 1)
    except (ValueError, IndexError):
        return None
    return (as_of.year - y) * 12 + (as_of.month - m)


def lint_research(brief, as_of=None):
    """Return (fails, warns). Empty fails = passes the mechanical gate."""
    fails, warns = [], []

    angle = brief.get("angle", "").strip()
    if not angle:
        fails.append("no angle - a brief needs a specific take, not just a topic")
    elif any(m in angle.lower() for m in SLOP_ANGLE):
        fails.append("angle reads like a generic roundup - LinkedIn suppresses that as slop")

    items = brief.get("items", [])
    if not items:
        fails.append("no items")

    for it in items:
        name = it.get("name", "?")
        src = str(it.get("primary_source", "")).strip()
        verified = str(it.get("verified", "")).strip()
        claim = (str(it.get("claim", "")) + " " + str(it.get("metric", ""))).lower()
        src_is_primary = bool(src) and any(h in src for h in PRIMARY_HOSTS)

        if not src:
            fails.append(f"{name}: no primary source URL - every claim traces to a source")
        elif not src_is_primary:
            warns.append(f"{name}: source is not a primary host ({src}) - confirm on the repo/docs/card")

        if not verified:
            fails.append(f"{name}: no verification note - was the source actually opened this session?")
        if it.get("metric") and not verified:
            fails.append(f"{name}: cites a number ({it['metric']}) with nothing saying it was verified")

        if any(s in claim for s in SUPERLATIVE) and not src_is_primary:
            fails.append(f"{name}: superlative claim without a primary source - drop it or cite one")

        # Freshness by VELOCITY (from gh_metrics) when present; recency date is the fallback.
        trend = str(it.get("trend", "")).strip().upper()
        if trend:
            if not any(g in trend for g in GOOD_TREND):
                fails.append(f"{name}: trend '{it['trend']}' is not gaining now (velocity gate)")
        else:
            months = _months_since(it.get("recency"), as_of)
            if months is None:
                fails.append(f"{name}: no trend metric and no valid recency date - freshness unknown")
            elif months > STALE_MONTHS_FAIL:
                fails.append(f"{name}: ~{months} months old - stale; a post is news, not a history lesson")
            elif months > STALE_MONTHS_WARN:
                warns.append(f"{name}: ~{months} months old - aging; make sure the hook is genuinely fresh")

    return fails, warns


def _selftest():
    today = date(2026, 7, 6)
    good = {"topic": "a free dev tool that went viral in 2026",
            "angle": "the four coding rules I already run daily, turned into 188k stars",
            "items": [{"name": "andrej-karpathy-skills", "claim": "one CLAUDE.md, four rules",
                       "metric": "188000 stars", "recency": "2026-01-27",
                       "primary_source": "https://github.com/multica-ai/andrej-karpathy-skills",
                       "verified": "fetched repo 2026-07-06; 188k, MIT, four rules confirmed"}]}
    f, w = lint_research(good, today); assert not f, f

    stale = {"topic": "x", "angle": "solid picks",
             "items": [dict(good["items"][0], recency="2023-02-01")]}
    assert any("stale" in x for x in lint_research(stale, today)[0])

    unver = {"topic": "x", "angle": "solid picks",
             "items": [{"name": "MysteryTool", "claim": "huge", "metric": "1000000 stars",
                        "recency": "2026-06-01", "primary_source": "", "verified": ""}]}
    f, _ = lint_research(unver, today)
    assert any("no primary source" in x for x in f) and any("verification" in x for x in f), f

    slop = {"topic": "x", "angle": "top 10 AI tools you should know",
            "items": [good["items"][0]]}
    assert any("roundup" in x for x in lint_research(slop, today)[0])

    superl = {"topic": "x", "angle": "a real take",
              "items": [{"name": "HypeTool", "claim": "the most starred repo in history",
                         "metric": "400000 stars", "recency": "2026-05-01",
                         "primary_source": "https://medium.com/some-listicle",
                         "verified": "read a blog"}]}
    assert any("superlative" in x for x in lint_research(superl, today)[0])

    cooling = {"topic": "x", "angle": "a real take",
               "items": [dict(good["items"][0], trend="COOLING - past its peak moment")]}
    assert any("velocity gate" in x for x in lint_research(cooling, today)[0])
    print("research_check selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", help="path to a research brief JSON file")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    if not a.brief:
        sys.exit("provide --brief <file.json> or --selftest")
    brief = json.loads(Path(a.brief).read_text())
    fails, warns = lint_research(brief)
    for w in warns:
        print(f"  warn: {w}")
    if fails:
        print("FAIL:")
        for x in fails:
            print(f"  - {x}")
        sys.exit(1)
    n = len(brief.get("items", []))
    print(f"PASS ({n} items). Mechanical gate clear - newsworthiness + fit still need human review (RESEARCH.md).")


if __name__ == "__main__":
    main()
