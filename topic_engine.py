#!/usr/bin/env python3
"""Topic engine - picks WHAT to post before any research or design happens.

The pipeline had gates for research (research_check), copy (check), and design
(palette/lint/score), but topic selection was vibes. This ranks the ideas.md
backlog by VALUE DENSITY so the best candidate - not the most recent thought -
graduates to a research brief.

  value = freshness x (utility/3) x (surprise/3) x (1 - novelty)

MULTIPLICATIVE on purpose: a zero on any axis kills the candidate. A stale
repeat with high utility still dies; "unmissable" means strong on EVERY axis.
(Rejected: weighted sum - it lets one loud axis mask a fatal weakness.)

Axes:
  - freshness : gh_metrics verdict for topics with a github url (EXPLODING best,
                COOLING/KNOWN nearly dead). Topics with no url (essays, glossaries)
                get a neutral EVERGREEN factor - they compete, but never outrank
                an exploding tool on freshness.
  - utility   : 0-3 judgment score set when the idea is added: can the reader
                ACT on this today? (3 = copy-paste actionable, 0 = trivia)
  - surprise  : 0-3 judgment score: does it contradict what the reader believes?
                (3 = contrarian with evidence, 0 = everyone already agrees)
  - novelty   : trigram similarity vs everything in tracking.csv (tracker.novelty).
                > 0.5 = re-posting yourself -> HARD BLOCK, same gate as post.py.

Backlog = ideas.md (human-editable markdown, one `## heading` per idea; see
_parse). Utility/surprise are set by whoever adds the idea. `--scout` suggests
new candidates from gh_metrics --trending.

  python3 topic_engine.py                 # rank the backlog (fetches gh where url present)
  python3 topic_engine.py --offline       # rank without network (freshness = evergreen)
  python3 topic_engine.py --scout "query" # suggest new candidates to paste into ideas.md
  python3 topic_engine.py --brief         # top candidate -> drafts/brief_<slug>.json skeleton
  python3 topic_engine.py --selftest
"""
import argparse, json, re, sys
from pathlib import Path

import config as _profile
import gh_metrics
import tracker

IDEAS = Path(__file__).parent / "ideas.md"
DRAFTS = Path(__file__).parent / "drafts"

# verdict keyword -> freshness factor. UNVERIFIED knobs - tune against engagement.
FRESHNESS = {
    "EXPLODING": 1.0,
    "RISING": 0.8,
    "STEADY": 0.4,
    "VELOCITY UNKNOWN": 0.5,
    "TOO THIN": 0.2,
    "COOLING": 0.1,
    "LIKELY KNOWN": 0.1,
}
EVERGREEN = 0.5        # no-url topics: essays, glossaries, war stories
NOVELTY_BLOCK = 0.5    # same threshold post.py blocks at


def _parse(text):
    """ideas.md -> candidate dicts. One idea per `## heading`; body lines are
    `- key: value` (url, angle, utility, surprise, status). Unknown keys kept."""
    ideas = []
    for block in re.split(r"^## +", text, flags=re.M)[1:]:
        lines = block.strip().splitlines()
        idea = {"name": lines[0].strip()}
        for ln in lines[1:]:
            m = re.match(r"- *(\w+) *: *(.+)", ln.strip())
            if m:
                idea[m.group(1).lower()] = m.group(2).strip()
        ideas.append(idea)
    return ideas


def _freshness(idea, offline=False):
    """(factor, label). An explicit `trend:` key wins (scout.py emits one for
    HN/HuggingFace finds - non-github sources would otherwise all flatten to
    EVERGREEN); else live gh_metrics verdict when the idea has a github url."""
    explicit = (idea.get("trend") or "").strip().upper()
    if explicit:
        for key, factor in FRESHNESS.items():
            if explicit.startswith(key):
                return factor, idea["trend"]
    url = idea.get("url", "")
    if "github.com" not in url:
        return EVERGREEN, "EVERGREEN (no repo - judgment freshness)"
    if offline:
        return EVERGREEN, "OFFLINE (repo not checked)"
    try:
        m = gh_metrics.metrics(url)
    except Exception as e:                       # rate limit / 404 / network
        return EVERGREEN, f"FETCH FAILED ({e}) - treated as evergreen"
    idea["stars_per_day"] = m["recent_per_day"] or 0   # tie-break within a verdict band
    verdict = m["verdict"]
    for key, factor in FRESHNESS.items():
        if verdict.startswith(key):
            return factor, verdict
    return EVERGREEN, verdict


def score(idea, offline=False):
    """Attach value-density score + per-axis breakdown to one idea dict."""
    utility = min(3, max(0, int(idea.get("utility", 0))))
    surprise = min(3, max(0, int(idea.get("surprise", 0))))
    # capability 0-3: can YOU demo YOUR OWN work with this topic? Build-stories
    # usually serve more account goals than news commentary. The factor
    # (0.4..1.0) boosts own-work without killing news - a soft axis, not a
    # hard gate like the others. UNVERIFIED knob - tune against tracker data.
    capability = min(3, max(0, int(idea.get("capability", 0))))
    cap_factor = (2 + capability) / 5
    fresh, fresh_label = _freshness(idea, offline)
    sim, closest = tracker.novelty(idea["name"] + " " + idea.get("angle", ""))
    blocked = sim > NOVELTY_BLOCK
    value = 0.0 if blocked else round(
        fresh * (utility / 3) * (surprise / 3) * (1 - sim) * cap_factor, 3)
    idea.update(value=value, freshness=fresh, freshness_label=fresh_label,
                utility=utility, surprise=surprise, capability=capability,
                novelty_sim=sim, novelty_closest=closest, blocked=blocked)
    return idea


def rank(offline=False, path=IDEAS):
    """Score every non-done idea in the backlog, best first."""
    if not path.exists():
        sys.exit(f"no backlog at {path} - create it (see module docstring)")
    ideas = [i for i in _parse(path.read_text())
             if i.get("status", "new") not in ("posted", "dropped")]
    return sorted((score(i, offline) for i in ideas),
                  key=lambda i: (i["value"], i.get("stars_per_day", 0)), reverse=True)


def brief_skeleton(idea):
    """research_check-shaped brief with the verification fields EMPTY - the
    research session must fill claim/metric/recency/verified; the gate stays."""
    return {
        "topic": idea["name"],
        "angle": idea.get("angle", ""),
        # creative engine: research fills WHO the story centers on (drives the
        # face ladder - never a company->CEO map) and the story type (visual class)
        "people": [],
        "story_type": "",   # person | product | company | number | concept
        "items": [{
            "name": idea["name"],
            "claim": "",
            "metric": "",
            "recency": "",
            "primary_source": idea.get("url", ""),
            "verified": "",
            "trend": idea.get("freshness_label", ""),
        }],
    }


def _print_ranked(ranked):
    for i, r in enumerate(ranked, 1):
        flag = "  BLOCKED (repeat)" if r["blocked"] else ""
        print(f"{i}. [{r['value']:.3f}] {r['name']}{flag}")
        spd = f"  {r['stars_per_day']:.0f} stars/day" if r.get("stars_per_day") else ""
        print(f"     fresh={r['freshness']:.2f} ({r['freshness_label']}){spd}  "
              f"utility={r['utility']}/3  surprise={r['surprise']}/3  "
              f"novelty_sim={r['novelty_sim']}"
              + (f" ~ '{r['novelty_closest']}'" if r['novelty_sim'] > 0.2 else ""))
        if r.get("angle"):
            print(f"     angle: {r['angle']}")
    if not ranked:
        print("backlog is empty - add ideas to ideas.md or run --scout")


def _scout(query, since):
    print(f"# recently-created repos for '{query}' (paste keepers into ideas.md):\n")
    for r in gh_metrics.trending(query, since):
        print(f"## {r['repo'].split('/')[-1]}\n"
              f"- url: https://github.com/{r['repo']}\n"
              f"- angle: \n- utility: \n- surprise: \n"
              f"- note: {r['stars']} stars, created {r['created']} - {r['desc']}\n")


def _selftest():
    ideas = _parse("# backlog\n\n## Tool X\n- url: https://github.com/a/b\n"
                   "- angle: the take\n- utility: 3\n- surprise: 2\n\n"
                   "## Old essay\n- status: posted\n- utility: 3\n- surprise: 3\n")
    assert ideas[0]["name"] == "Tool X" and ideas[0]["utility"] == "3"
    assert ideas[1]["status"] == "posted"
    # evergreen scoring, offline: 0.5 * 3/3 * 2/3 * (1 - sim) * cap_factor
    s = score({"name": "a topic no post has ever mentioned zzqx",
               "angle": "unique angle", "utility": "3", "surprise": "2"}, offline=True)
    assert not s["blocked"] and 0 < s["value"] <= 0.5 * (2 / 3), s["value"]
    # capability axis: own-work (3) outranks identical news (absent -> 0), 1.0 vs 0.4
    hi = score({"name": "own build zzqx unique", "angle": "x", "utility": "3",
                "surprise": "2", "capability": "3"}, offline=True)
    lo = score({"name": "news item zzqx unique", "angle": "y", "utility": "3",
                "surprise": "2"}, offline=True)
    assert hi["value"] > lo["value"] > 0 and abs(hi["value"] / lo["value"] - 2.5) < 0.1
    # explicit trend key (from scout.py) beats the EVERGREEN fallback for non-github urls
    tr = score({"name": "hf model zzqx unique", "angle": "z", "utility": "3",
                "surprise": "2", "url": "https://huggingface.co/x/y",
                "trend": "EXPLODING - top of trending"}, offline=True)
    assert tr["freshness"] == 1.0, tr["freshness_label"]
    # a zero axis kills the candidate (multiplicative)
    z = score({"name": "zero surprise zzqx", "utility": "3", "surprise": "0"}, offline=True)
    assert z["value"] == 0.0
    # repeat of a real logged post hard-blocks (uses live tracking.csv copy_hook)
    rows = tracker._read()
    if rows and rows[0].get("copy_hook"):
        hook = rows[0]["copy_hook"]
        b = score({"name": hook, "angle": hook, "utility": "3", "surprise": "3"},
                  offline=True)
        assert b["blocked"] and b["value"] == 0.0
    sk = brief_skeleton({"name": "Tool X", "angle": "t", "url": "u",
                         "freshness_label": "RISING"})
    assert sk["items"][0]["verified"] == "" and sk["items"][0]["trend"] == "RISING"
    assert sk["people"] == [] and sk["story_type"] == ""   # creative-engine fields
    print("topic_engine selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip gh fetches")
    ap.add_argument("--scout", nargs="?", const=_profile.P["niche"]["gh_scout_query"],
                    metavar="QUERY")
    ap.add_argument("--since", type=int, default=60, help="scout: created within N days")
    ap.add_argument("--brief", action="store_true",
                    help="write drafts/brief_<slug>.json for the top candidate")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    if a.scout is not None:
        _scout(a.scout, a.since); return
    ranked = rank(a.offline)
    _print_ranked(ranked)
    if a.brief and ranked and not ranked[0]["blocked"] and ranked[0]["value"] > 0:
        top = ranked[0]
        slug = re.sub(r"\W+", "_", top["name"].lower()).strip("_")[:40]
        DRAFTS.mkdir(exist_ok=True)
        out = DRAFTS / f"brief_{slug}.json"
        out.write_text(json.dumps(brief_skeleton(top), indent=2))
        print(f"\nbrief skeleton -> {out}  (research fills claim/metric/recency/verified,"
              f"\n then: python3 research_check.py --brief {out.name})")


if __name__ == "__main__":
    main()
