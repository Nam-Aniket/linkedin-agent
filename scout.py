#!/usr/bin/env python3
"""Multi-source topic scout - fixes the GitHub-only discovery bias.

Sources (all free, no auth; verified live 2026-07-08):
  hn     Hacker News via the Algolia search API - stories with points/comments
         velocity. Yields Show-HN tools, cost-pain threads, contrarian material.
  hf     HuggingFace trending models - model releases before they hit LinkedIn.
  (GitHub stays in gh_metrics.py; topic_engine --scout wraps it.)

Every source's raw signal lives on its own scale (HN points vs stars/day vs
trendingScore), so each is BANDED to the same verdict labels topic_engine and
research_check already understand (EXPLODING/RISING/STEADY/TOO THIN). Compare
normalized, never raw. Band thresholds are UNVERIFIED knobs - tune against
engagement once the tracker has data.

Dual use: `pain` searches HN for people publicly feeling the pains YOUR niche
cares about (profile.json niche.pain_queries) - each hit is BOTH a contrarian-
post hook AND a prospect signal. Hits append to drafts/pain_signals.jsonl.

  python3 scout.py hn "agent memory" --days 7 --min-points 50
  python3 scout.py hf
  python3 scout.py pain --days 7
  python3 scout.py floor          # backlog full enough? top-up candidates if not
  python3 scout.py --selftest
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import config as _profile

DRAFTS = Path(__file__).parent / "drafts"
PAIN_LOG = DRAFTS / "pain_signals.jsonl"
_NICHE = _profile.P["niche"]
BACKLOG_FLOOR = _NICHE["backlog_floor"]   # a 1/day takt wants ~a week of ready topics
DEFAULT_QUERY = _NICHE["hn_query"]


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "topic-scout/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# --- per-source banding: raw signal -> the shared verdict vocabulary ------------
# (labels must satisfy research_check.GOOD_TREND so briefs pass the velocity gate)

def band_hn(points_per_day):
    """HN: points/day since posting. UNVERIFIED knobs."""
    if points_per_day >= 200:
        return "EXPLODING - front-page velocity right now"
    if points_per_day >= 75:
        return "RISING - gaining steadily"
    if points_per_day >= 20:
        return "STEADY - alive but not hot"
    return "TOO THIN - little traction"


def band_hf(trending_score):
    """HuggingFace trendingScore. UNVERIFIED knobs (top-3 observed 420-589)."""
    if trending_score >= 400:
        return "EXPLODING - top of trending"
    if trending_score >= 150:
        return "RISING - climbing trending"
    if trending_score >= 50:
        return "STEADY - some pull"
    return "TOO THIN - background noise"


# --- sources ---------------------------------------------------------------------

def hn(query, days=7, min_points=50, limit=8):
    """Recent HN stories for a query, velocity-banded, best first."""
    since = int((dt.datetime.now() - dt.timedelta(days=days)).timestamp())
    url = ("https://hn.algolia.com/api/v1/search_by_date?"
           + urllib.parse.urlencode({
               "query": query, "tags": "story",
               "numericFilters": f"points>{min_points},created_at_i>{since}",
               "hitsPerPage": 50}))
    hits = _get_json(url).get("hits", [])
    out = []
    now = dt.datetime.now(dt.timezone.utc)
    for h in hits:
        created = dt.datetime.fromisoformat(h["created_at"].replace("Z", "+00:00"))
        age_days = max((now - created).total_seconds() / 86400, 0.1)
        ppd = round((h.get("points") or 0) / age_days, 1)
        out.append({
            "source": "hn", "title": h.get("title", ""),
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
            "hn_url": f"https://news.ycombinator.com/item?id={h['objectID']}",
            "points": h.get("points") or 0, "comments": h.get("num_comments") or 0,
            "created": h["created_at"][:10], "points_per_day": ppd,
            "trend": band_hn(ppd),
        })
    out.sort(key=lambda x: -x["points_per_day"])
    return out[:limit]


def hf(limit=8):
    """HuggingFace trending models, banded."""
    models = _get_json("https://huggingface.co/api/models?sort=trendingScore"
                       f"&direction=-1&limit={limit}")
    return [{
        "source": "hf", "title": m.get("id", ""),
        "url": f"https://huggingface.co/{m.get('id','')}",
        "trending_score": m.get("trendingScore") or 0,
        "likes": m.get("likes") or 0, "downloads": m.get("downloads") or 0,
        "created": (m.get("createdAt") or "")[:10],
        "trend": band_hf(m.get("trendingScore") or 0),
    } for m in models]


# --- dual use: pain signals (content hook + prospect signal) ----------------------

PAIN_QUERIES = _NICHE["pain_queries"]


def pain(days=14, min_comments=10):
    """HN threads where someone is publicly feeling AI cost/reliability pain.
    Each is a contrarian-post hook AND a prospect signal (appended to jsonl)."""
    seen, out = set(), []
    for q in PAIN_QUERIES:
        try:
            for h in hn(q, days=days, min_points=10, limit=10):
                if h["hn_url"] in seen or h["comments"] < min_comments:
                    continue
                seen.add(h["hn_url"])
                out.append(h)
        except Exception as e:   # one dead query must not kill the sweep
            print(f"  [pain] query '{q}' failed: {e}", file=sys.stderr)
    out.sort(key=lambda x: -x["comments"])   # pain = people TALKING about it
    DRAFTS.mkdir(exist_ok=True)
    with open(PAIN_LOG, "a") as f:
        for h in out:
            f.write(json.dumps({**h, "logged": dt.date.today().isoformat()}) + "\n")
    return out


# --- own-work scout: the ANCHOR source ---------------------------------------------
# Build-stories (things YOU shipped) usually outperform news commentary. Three
# mines, all configured in profile.json own_work (empty = this source stays off):
# git activity in your project repos (auto-discovered, activity-filtered so dead
# repos never surface), a failure log (war stories - root cause + rule = a post
# skeleton), and a learning log (explainer candidates).

_OWN = _profile.P["own_work"]
OWN_ROOTS = [Path(p).expanduser() for p in _OWN["repo_roots"]]   # scanned 1 level deep
REPO_ALIAS = dict(_OWN["repo_alias"])
FAILURE_LOG = Path(_OWN["failure_log"]).expanduser() if _OWN["failure_log"] else Path("/nonexistent")
LEARNING_LOG = Path(_OWN["learning_log"]).expanduser() if _OWN["learning_log"] else Path("/nonexistent")
_HEAD_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2})\s*[-—]\s*(.+)$", re.M)


def band_own(age_days):
    """Own work: freshness = how recently it shipped. UNVERIFIED knobs."""
    if age_days <= 3:
        return "EXPLODING - shipped in the last 3 days"
    if age_days <= 14:
        return "RISING - recent own work"
    return "STEADY - own work, aging"


def _repo_activity(days=14):
    """Project repos with real recent commits (dir scan + git log)."""
    seen, out = set(), []
    for root in OWN_ROOTS:
        for p in root.iterdir() if root.exists() else []:
            if not (p / ".git").is_dir() or str(p) in seen:
                continue
            seen.add(str(p))
            try:
                log = subprocess.run(
                    ["git", "-C", str(p), "log", f"--since={days} days ago",
                     "--format=%cs %s"],
                    capture_output=True, text=True, timeout=10).stdout.strip()
            except Exception:
                continue
            lines = [ln for ln in log.splitlines() if len(ln) > 11]
            if not lines:
                continue        # the activity filter: no recent commits = invisible
            age = (dt.date.today() - dt.date.fromisoformat(lines[0][:10])).days
            out.append({"name": REPO_ALIAS.get(p.name, p.name), "path": str(p),
                        "commits": len(lines), "age": age,
                        "subjects": [ln[11:] for ln in lines[:5]]})
    out.sort(key=lambda r: -r["commits"])
    return out


def _log_entries(path, days, seed_key):
    """Parse '### YYYY-MM-DD - title' entries newer than `days`; pull the line
    tagged `seed_key` (e.g. 'The rule:', 'In one line:') as angle material."""
    if not Path(path).exists():
        return []
    text = Path(path).read_text()
    cutoff = dt.date.today() - dt.timedelta(days=days)
    out = []
    for m in _HEAD_RE.finditer(text):
        d = dt.date.fromisoformat(m.group(1))
        if d < cutoff:
            continue
        tail = text[m.end():m.end() + 700]
        nxt = tail.find("\n### ")          # never read past this entry into the next
        if nxt != -1:
            tail = tail[:nxt]
        sm = re.search(re.escape(seed_key) + r"\*\*\s*(.+)", tail)
        out.append({"date": m.group(1),
                    "title": m.group(2).replace("—", "-").strip(),
                    "seed": (sm.group(1).strip() if sm else "")[:140],
                    "age": (dt.date.today() - d).days})
    return out


def own(days=14, per_bucket=5):
    """Own-work candidates as paste-ready ideas.md blocks (capability preset).
    Logs are newest-at-top, so [:per_bucket] keeps the freshest of each bucket -
    a shortlist to curate, not a firehose (200 raw candidates observed)."""
    blocks = []
    for r in _repo_activity(days)[:per_bucket]:
        blocks.append(
            f"## {r['name']}: {r['subjects'][0][:50]}\n"
            f"- angle: \n- utility: \n- surprise: \n- capability: 3\n"
            f"- trend: {band_own(r['age'])}\n"
            f"- note: own repo ({r['commits']} commits/{days}d): "
            + "; ".join(s[:45] for s in r["subjects"][:3]) + "\n")
    for e in _log_entries(FAILURE_LOG, days, "The rule:")[:per_bucket]:
        blocks.append(
            f"## war story: {e['title'][:55]}\n"
            f"- angle: {e['seed']}\n- utility: \n- surprise: \n- capability: 3\n"
            f"- trend: {band_own(e['age'])}\n- note: failure-log {e['date']}\n")
    for e in _log_entries(LEARNING_LOG, days, "In one line:")[:per_bucket]:
        blocks.append(
            f"## explainer: {e['title'][:55]}\n"
            f"- angle: {e['seed']}\n- utility: \n- surprise: \n- capability: 2\n"
            f"- note: learning-log {e['date']} (evergreen explainer)\n")
    return blocks


# --- backlog floor (the takt guard) ----------------------------------------------

def ready_count():
    """Ideas in ideas.md not yet posted/dropped."""
    import topic_engine
    if not topic_engine.IDEAS.exists():
        return 0
    return len([i for i in topic_engine._parse(topic_engine.IDEAS.read_text())
                if i.get("status", "new") not in ("posted", "dropped")])


def idea_block(item):
    """Format a scouted item as a paste-ready ideas.md block."""
    note = (f"{item['points']}pts/{item['comments']}c, {item['points_per_day']}/day"
            if item["source"] == "hn"
            else f"trending={item['trending_score']}, {item['likes']} likes")
    return (f"## {item['title'][:60]}\n"
            f"- url: {item['url']}\n"
            f"- angle: \n- utility: \n- surprise: \n- capability: 0\n"
            f"- trend: {item['trend']}\n"
            f"- note: {item['source']} {item['created']} - {note}\n")


def floor(days=7):
    """Takt guard: report backlog depth; print top-up candidates when below floor."""
    n = ready_count()
    print(f"backlog: {n} ready topics (floor {BACKLOG_FLOOR})")
    if n >= BACKLOG_FLOOR:
        print("backlog full - nothing to do.")
        return
    print(f"\nneed {BACKLOG_FLOOR - n} more - candidates (paste keepers into ideas.md,"
          f"\nset angle/utility/surprise/capability yourself):\n")
    print("--- own work (the anchor - build-stories beat news commentary):\n")
    for blk in own(days)[:4]:
        print(blk)
    print("--- external (tool-scout material):\n")
    for item in hn(DEFAULT_QUERY, days=days)[:3] + hf(3):
        print(idea_block(item))


# --- selftest (offline - pure functions only) -------------------------------------

def _selftest():
    assert band_hn(250).startswith("EXPLODING") and band_hn(80).startswith("RISING")
    assert band_hn(25).startswith("STEADY") and band_hn(3).startswith("TOO THIN")
    assert band_hf(500).startswith("EXPLODING") and band_hf(60).startswith("STEADY")
    blk = idea_block({"source": "hn", "title": "Some Tool", "url": "https://x.com",
                      "points": 100, "comments": 40, "points_per_day": 90.0,
                      "created": "2026-07-01", "trend": "RISING - gaining steadily"})
    assert blk.startswith("## Some Tool") and "- capability: 0" in blk and "90.0/day" in blk
    assert "- trend: RISING" in blk   # topic_engine reads this key for freshness
    blk2 = idea_block({"source": "hf", "title": "org/model", "url": "https://x.com",
                       "trending_score": 420, "likes": 5, "created": "2026-07-01",
                       "trend": "EXPLODING - top of trending"})
    assert "trending=420" in blk2
    # bands emit labels research_check's velocity gate accepts
    import research_check
    assert any(g in band_hn(80) for g in research_check.GOOD_TREND)
    assert any(g in band_hf(500) for g in research_check.GOOD_TREND)
    assert any(g in band_own(2) for g in research_check.GOOD_TREND)
    # own-work log parsing: both dash styles, seed extraction, date cutoff
    import tempfile
    p = Path(tempfile.mkdtemp()) / "log.md"
    today = dt.date.today().isoformat()
    p.write_text(f"### {today} - fresh entry\n- **The rule:** grep sibling paths\n"
                 f"- **Cost:** none\n\n"
                 f"### {today} — em dash entry\n- **In one line:** the idea, plainly\n\n"
                 f"### 2020-01-01 - ancient entry\n- **The rule:** too old to surface\n")
    rules = _log_entries(p, 14, "The rule:")
    # ancient entry filtered by date; entry lacking the seed key stays (title is
    # still a candidate) but must NOT steal the seed from the entry after it
    assert len(rules) == 2, rules
    assert rules[0]["seed"] == "grep sibling paths" and rules[1]["seed"] == "", rules
    ones = _log_entries(p, 14, "In one line:")
    assert [e["seed"] for e in ones] == ["", "the idea, plainly"], ones
    assert ones[1]["title"] == "em dash entry"       # em dash heading parses
    assert _log_entries(p / "nope.md", 14, "x") == []
    print("scout selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", choices=["hn", "hf", "pain", "floor", "own"])
    ap.add_argument("query", nargs="?", default=DEFAULT_QUERY)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-points", type=int, default=50)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    if a.cmd == "hn":
        for h in hn(a.query, a.days, a.min_points):
            print(f"[{h['points_per_day']:>6}/day] {h['title'][:64]}\n"
                  f"    {h['points']}pts {h['comments']}c {h['created']}  {h['trend']}\n"
                  f"    {h['url']}")
    elif a.cmd == "hf":
        for m in hf():
            print(f"[{m['trending_score']:>4}] {m['title'][:64]}  "
                  f"{m['likes']} likes  {m['trend']}")
    elif a.cmd == "pain":
        hits = pain(a.days)
        print(f"{len(hits)} pain signals (also appended to {PAIN_LOG.name}):")
        for h in hits:
            print(f"[{h['comments']:>4}c] {h['title'][:64]}\n    {h['hn_url']}")
    elif a.cmd == "own":
        blocks = own(a.days)
        print(f"{len(blocks)} own-work candidates (last {a.days}d):\n")
        for blk in blocks:
            print(blk)
    elif a.cmd == "floor":
        floor(a.days)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
