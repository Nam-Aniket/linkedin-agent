#!/usr/bin/env python3
"""Fetch volume + velocity + trend for a GitHub repo, so the research eval can catch
tools that are gaining NOW and skip ones that peaked months ago (popular, but everyone
already knows them).

Freshness is not age. A repo 2 months old and accelerating beats one 5 months old that
already flattened. GitHub has no "star velocity" endpoint, so we reconstruct the recent
growth rate from recent star events (WatchEvents) in the repo events feed:
  - volume       : current stars (enough traction to matter yet?)
  - avg_per_day   : stars / age  (lifetime rate)
  - recent_per_day: rate over the most recent stargazers (current rate)
  - acceleration  : recent_per_day / avg_per_day  (>1 = still speeding up = rising)

Uses the GitHub API with a token from $GITHUB_TOKEN or the gh CLI when available
(the events feed rate-limits fast unauth). The stargazers-timestamps endpoint this
originally used was withdrawn by GitHub (~2026-07, 404s even authed); velocity now
comes from WatchEvents in the events feed (newest ~300 events / 90 days).

  python3 gh_metrics.py https://github.com/owner/repo
  python3 gh_metrics.py --selftest
"""
import argparse, json, os, sys, re, subprocess, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta

GH = "https://api.github.com"

_token_cache = []          # [token-or-None], filled on first use


def _token():
    """GitHub token from $GITHUB_TOKEN or the gh CLI, else None. Since 2026-07 the
    stargazers endpoint (our velocity source) 401s without auth; a token also lifts
    the rate limit 60/hr -> 5000/hr. Never printed."""
    if not _token_cache:
        t = os.environ.get("GITHUB_TOKEN")
        if not t:
            try:
                t = subprocess.run(["gh", "auth", "token"], capture_output=True,
                                   text=True, timeout=5).stdout.strip() or None
            except (OSError, subprocess.TimeoutExpired):
                t = None
        _token_cache.append(t)
    return _token_cache[0]
# All knobs below are UNVERIFIED - tune against real engagement.
VOLUME_FLOOR = 500          # under this, too thin to be newsworthy
YOUNG_DAYS = 75             # under this age, high volume = exploding, not "known"
DISCOVERY_MAX = 60000       # over this AND older than YOUNG_DAYS, the audience already saw it
RISING_ACCEL = 1.3          # recent rate must beat lifetime avg by this to count as rising
COOLING_ACCEL = 0.7         # under this, it has passed its moment


def _get(url, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "linkedin-research-eval",
               "X-GitHub-Api-Version": "2022-11-28"}
    if _token():
        headers["Authorization"] = "Bearer " + _token()
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def _parse_repo(url):
    m = re.search(r"github\.com/([^/]+)/([^/#?]+)", url)
    if not m:
        raise ValueError(f"not a github repo url: {url}")
    name = m.group(2)
    return m.group(1), name[:-4] if name.endswith(".git") else name


def _days(iso, now):
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return max(0.5, (now - dt).total_seconds() / 86400)


def _recent_velocity(owner, repo, stars, now):
    """Stars/day from recent WatchEvents (= stars) in the repo events feed.
    The stargazers-timestamps endpoint 404s as of 2026-07 (GitHub withdrew it),
    so we count star events over the feed's span instead. The feed holds the
    newest ~300 events / 90 days - for hot repos that's a short, CURRENT window,
    which is exactly what recent velocity means. None if not measurable."""
    watch, oldest = 0, None
    try:
        for page in (1, 2, 3):                    # events API caps at 300 events
            data = _get(f"{GH}/repos/{owner}/{repo}/events?per_page=100&page={page}")
            if not data:
                break
            for ev in data:
                if ev.get("type") == "WatchEvent":
                    watch += 1
                oldest = ev["created_at"]         # feed is newest-first
            if _days(oldest, now) > 7:            # a week of signal is plenty
                break
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):             # rate-limited / gone: unknown,
            return None                           # stars/age/verdict still stand
        raise
    if watch < 2 or oldest is None:
        return None
    return watch / _days(oldest, now)             # _days floors at 0.5 day


def _verdict(stars, age, recent_v, accel):
    if stars < VOLUME_FLOOR:
        return "TOO THIN - not enough traction yet to be newsworthy"
    if age <= YOUNG_DAYS:
        return "EXPLODING - young and already big; peak freshness, post it now"
    if stars > DISCOVERY_MAX:
        return "LIKELY KNOWN - big enough that most of the audience already saw it"
    if recent_v is None:
        return "VELOCITY UNKNOWN - could not sample recent stars"
    if accel >= RISING_ACCEL:
        return "RISING - gaining faster than its own average; catch it now"
    if accel <= COOLING_ACCEL:
        return "COOLING - past its peak moment; stale signal"
    return "STEADY - popular but not accelerating; a weak hook"


def metrics(url, now=None):
    now = now or datetime.now(timezone.utc)
    owner, repo = _parse_repo(url)
    info = _get(f"{GH}/repos/{owner}/{repo}")
    stars, age = info["stargazers_count"], _days(info["created_at"], now)
    avg_v = stars / age
    recent_v = _recent_velocity(owner, repo, stars, now)
    accel = (recent_v / avg_v) if (recent_v and avg_v) else None
    return {
        "repo": f"{owner}/{repo}", "stars": stars, "age_days": round(age),
        "avg_per_day": round(avg_v, 1),
        "recent_per_day": round(recent_v, 1) if recent_v else None,
        "acceleration": round(accel, 2) if accel else None,
        "verdict": _verdict(stars, age, recent_v, accel),
    }


def trending(query="llm OR agent OR rag", since_days=90, limit=12, now=None):
    """Discover repos CREATED recently, ranked by stars - i.e. new AND already popular.
    The discovery half: listicles surface famous repos; this surfaces the rising ones."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=since_days)).strftime("%Y-%m-%d")
    q = urllib.parse.quote(f"{query} created:>{since}")
    data = _get(f"{GH}/search/repositories?q={q}&sort=stars&order=desc&per_page={limit}")
    return [{"repo": r["full_name"], "stars": r["stargazers_count"],
             "created": r["created_at"][:10], "desc": (r.get("description") or "")[:70]}
            for r in data.get("items", [])]


def _selftest():
    assert "TOO THIN" in _verdict(100, 300, None, None)
    assert "EXPLODING" in _verdict(75000, 24, None, None)      # young + big (ponytail-shaped)
    assert "LIKELY KNOWN" in _verdict(200000, 400, None, None)
    assert "RISING" in _verdict(5000, 200, 80, 2.0)
    assert "COOLING" in _verdict(5000, 200, 5, 0.4)
    assert "STEADY" in _verdict(5000, 200, 30, 1.0)
    assert _parse_repo("https://github.com/multica-ai/andrej-karpathy-skills") == \
        ("multica-ai", "andrej-karpathy-skills")
    print("gh_metrics selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--trending", nargs="?", const="llm OR agent OR rag", metavar="QUERY",
                    help="discover recently-created repos ranked by stars")
    ap.add_argument("--since", type=int, default=90, help="trending: created within N days")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    try:
        if a.trending is not None:
            for r in trending(a.trending, a.since):
                print(f"  {r['stars']:>6}  {r['repo']:<38} {r['created']}  {r['desc']}")
            return
        if not a.url:
            sys.exit("provide a github repo url, --trending QUERY, or --selftest")
        for k, v in metrics(a.url).items():
            print(f"  {k}: {v}")
    except urllib.error.HTTPError as e:
        sys.exit(f"GitHub API error {e.code}: {e.read().decode()[:200]}")


if __name__ == "__main__":
    main()
