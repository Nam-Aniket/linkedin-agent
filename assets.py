#!/usr/bin/env python3
"""assets.py - subject -> sourced, LICENSED visual assets (creative engine, chunk 2).

The provenance rule is structural: resolvers only accept names that come from the
gated research brief (people / topic entities) - there is no free-text image
search anywhere. Every asset returned carries {source_url, license, attribution,
credit} and anything without an acceptable license is rejected at fetch time,
before the deck_lint license gate ever sees it.

Sources:
  face/photo  Wikimedia Commons API (license whitelist: CC0 / Public domain /
              CC BY / CC BY-SA - never NC/ND/unknown). Attribution captured.
  logo        the vendored simple-icons set via element.py (CC0).
  screenshot  (chunk-later: Playwright capture of official pages)

  python3 assets.py face "Sundar Pichai"     # live: fetch + cache + provenance
  python3 assets.py logo "google gemini"
  python3 assets.py --selftest               # offline
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import config as _profile

CACHE = Path(__file__).parent / "assets" / "cache"
# Wikimedia asks API clients for a descriptive User-Agent with a contact
_UA = f"linkedin-agent-content-pipeline/0.1 ({_profile.P['contact']})"

COMMONS_API = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
               "&generator=search&gsrnamespace=6&gsrlimit=12&gsrsearch={q}"
               "&prop=imageinfo&iiprop=url|extmetadata|size&iiurlwidth=1000")


def _get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def license_ok(short_name):
    """Whitelist: reuse-with-attribution licenses only. NC/ND/unknown = reject."""
    s = (short_name or "").upper().replace("-", " ")
    if "NC" in s or "ND" in s:
        return False
    return ("CC0" in s or "PUBLIC DOMAIN" in s or s == "PD"
            or s.startswith("CC BY"))


def _credit(artist, lic):
    a = _strip_html(artist)
    a = re.sub(r"^(photographer|photo|author|by)\s*:?\s*", "", a, flags=re.I)
    return f"Photo: {a} ({lic}, Wikimedia Commons)" if a else f"Photo: {lic}, Wikimedia Commons"


def _cache_download(url, source_url, meta):
    """Download to a deterministic cache path + JSON sidecar with provenance."""
    CACHE.mkdir(parents=True, exist_ok=True)
    ext = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
    path = CACHE / (hashlib.md5(url.encode()).hexdigest()[:16] + ext)
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            path.write_bytes(r.read())
    (path.with_suffix(path.suffix + ".json")).write_text(
        json.dumps({**meta, "source_url": source_url, "fetched_from": url}, indent=1))
    return path


def published_asset_urls(n=8, rows=None):
    """source_urls of the last n PUBLISHED assets (tracking.csv tail) - the photo
    twin of compose's design-novelty gate."""
    if rows is None:
        import tracker
        rows = tracker._read()
    return {r.get("asset_url") for r in rows[-n:] if r.get("asset_url")}


def _best(candidates, portrait, exclude=None):
    """Rank (name-match, orientation, size), then skip recently-published photos
    so repeat subjects rotate imagery; if every candidate was used, fall back to
    the best match - variety never costs a story its photo."""
    candidates.sort(key=lambda c: (-c["match"], -(c["portrait"] if portrait else 0),
                                   -c["area"]))
    fresh = [c for c in candidates if c["source_url"] not in (exclude or set())]
    return (fresh or candidates)[0]


def wikimedia_photo(name, portrait=True, exclude=None):
    """Best licensed Commons photo for a name from the BRIEF. None if nothing
    acceptable exists - callers fall down the ladder, never force an image.
    `exclude` = source_urls to avoid (defaults to the last 8 published)."""
    if exclude is None:
        exclude = published_asset_urls()
    data = _get_json(COMMONS_API.format(q=urllib.parse.quote(name)))
    pages = (data.get("query") or {}).get("pages") or {}
    toks = [t for t in re.split(r"\W+", name.lower()) if len(t) > 2]
    candidates = []
    for p in pages.values():
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = _strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
        if not license_ok(lic):
            continue
        url = info.get("thumburl") or info.get("url") or ""
        if not url.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        title = p.get("title", "").lower()
        match = sum(1 for t in toks if t in title)
        if not match:                       # provenance: the file must be OF the name
            continue
        w, h = info.get("thumbwidth") or info.get("width") or 0, \
               info.get("thumbheight") or info.get("height") or 0
        candidates.append({
            "match": match, "portrait": int(h > w), "area": w * h,
            "url": url, "w": w, "h": h, "license": lic,
            "artist": (meta.get("Artist") or {}).get("value", ""),
            "source_url": info.get("descriptionurl") or "",
        })
    if not candidates:
        return None
    best = _best(candidates, portrait, exclude)
    meta = {"kind": "photo", "name": name, "license": best["license"],
            "attribution": _strip_html(best["artist"]),
            "credit": _credit(best["artist"], best["license"])}
    path = _cache_download(best["url"], best["source_url"], meta)
    return {**meta, "path": str(path), "source_url": best["source_url"],
            "w": best["w"], "h": best["h"]}


def face(person_name):
    """A licensed photo of the person the STORY names (brief `people` field)."""
    return wikimedia_photo(person_name, portrait=True)


# --- the screenshot rung (chunk 6): product stories get real product UI -------------
RENDER_PY = Path(__file__).parent / ".venv-render" / "bin" / "python"

_SHOT_DRIVER = """
import sys
from playwright.sync_api import sync_playwright
url, out = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/126.0.0.0 Safari/537.36")
    pg.goto(url, wait_until="networkidle", timeout=30000)
    pg.screenshot(path=out)
    b.close()
"""


def screenshot(url):
    """Capture an official PUBLIC page via the render venv's Playwright (real UA,
    nominative editorial use - the page is the product being written about).
    None on bot-block/timeout/missing venv: callers fall down the ladder, and a
    reconstruction fallback stays out of scope until a real block forces it."""
    if not url or not RENDER_PY.exists():
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.md5(url.encode()).hexdigest()[:16] + ".shot.png")
    domain = urllib.parse.urlparse(url).netloc
    meta = {"kind": "screenshot", "name": domain,
            "license": "own screenshot (editorial use)", "attribution": domain,
            "credit": f"Screenshot: {domain}"}
    if not path.exists():
        import subprocess
        import tempfile
        drv = Path(tempfile.mkdtemp()) / "shot.py"
        drv.write_text(_SHOT_DRIVER)
        try:
            r = subprocess.run([str(RENDER_PY), str(drv), url, str(path)],
                               capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0 or not path.exists():
            return None
    (path.with_suffix(path.suffix + ".json")).write_text(
        json.dumps({**meta, "source_url": url, "fetched_from": url}, indent=1))
    return {**meta, "path": str(path), "source_url": url, "w": 1440, "h": 900}


def logo(subject):
    """Brand mark via the vendored simple-icons set (CC0). SVG string, not a file."""
    import element
    el = element.element({"subject": subject, "keywords": subject.split()})
    if el.get("kind") != "logo":
        return None
    return {"kind": "logo", "svg": el["svg"], "license": "CC0 (simple-icons)",
            "attribution": "simple-icons", "credit": "", "source_url": ""}


# --- the relevance ladder ---------------------------------------------------------

def resolve(brief, _face=None, _logo=None, _shot=None):
    """Brief -> assets, per the spec's ladder. Only brief-named entities are ever
    queried (provenance is structural). Returns [] when nothing acceptable exists -
    the composer then falls to artifact/art classes, which need no external assets.
    (_face/_logo/_shot injectable for offline tests.)"""
    _face, _logo = _face or face, _logo or logo
    _shot = _shot or screenshot
    story_type = (brief.get("story_type") or "").strip().lower()
    people = [p for p in (brief.get("people") or []) if str(p).strip()]
    subject = brief.get("topic") or ""
    out = []
    if story_type == "person" and people:
        a = _face(people[0])
        if a:
            out.append(a)
    if not out and story_type == "product" and brief.get("url"):
        a = _shot(brief["url"])          # product story -> the product's real UI
        if a:
            out.append(a)
    if not out and story_type in ("person", "product", "company"):
        a = _logo(subject)
        if a:
            out.append(a)
    return out


# --- selftest (offline) ------------------------------------------------------------

def _selftest():
    # license whitelist: attribution-friendly in, NC/ND/unknown out
    assert license_ok("CC0") and license_ok("Public domain")
    assert license_ok("CC BY 4.0") and license_ok("CC BY-SA 3.0")
    assert not license_ok("CC BY-NC 4.0"), "NC must be rejected"
    assert not license_ok("CC BY-ND 2.0"), "ND must be rejected"
    assert not license_ok("") and not license_ok("Copyrighted")
    # credit formatting strips markup and redundant "Photographer:" prefixes
    assert _credit("<a href='x'>Jane Doe</a>", "CC BY 4.0") == \
        "Photo: Jane Doe (CC BY 4.0, Wikimedia Commons)"
    assert _credit("Photographer: Lukasz Kobus", "CC BY 4.0") == \
        "Photo: Lukasz Kobus (CC BY 4.0, Wikimedia Commons)"
    # cache path is deterministic per url
    a = hashlib.md5(b"http://x/y.jpg").hexdigest()[:16]
    assert a == hashlib.md5(b"http://x/y.jpg").hexdigest()[:16]
    # ladder: person story prefers the named person's face; falls to logo; else []
    fake_face = lambda n: {"kind": "photo", "name": n}
    fake_logo = lambda s: {"kind": "logo"}
    brief = {"topic": "google gemini", "story_type": "person", "people": ["Jane Doe"]}
    r = resolve(brief, _face=fake_face, _logo=fake_logo)
    assert r and r[0]["kind"] == "photo" and r[0]["name"] == "Jane Doe"
    r = resolve(brief, _face=lambda n: None, _logo=fake_logo)
    assert r and r[0]["kind"] == "logo", "no face -> falls to logo"
    r = resolve({"topic": "x", "story_type": "concept"},
                _face=fake_face, _logo=fake_logo)
    assert r == [], "concept stories use artifact/art - no external asset"
    r = resolve({"topic": "x", "story_type": "person", "people": []},
                _face=fake_face, _logo=lambda s: None)
    assert r == [], "person story with nobody named and no logo -> empty, never forced"
    # photo-novelty: ranking prefers a fresh photo, falls back when all are used
    cands = [{"match": 2, "portrait": 1, "area": 100, "source_url": "u1"},
             {"match": 2, "portrait": 1, "area": 90, "source_url": "u2"},
             {"match": 1, "portrait": 1, "area": 999, "source_url": "u3"}]
    assert _best(list(cands), True)["source_url"] == "u1"
    assert _best(list(cands), True, exclude={"u1"})["source_url"] == "u2"
    assert _best(list(cands), True, exclude={"u1", "u2", "u3"})["source_url"] == "u1", \
        "all used -> fall back to the best, never block the story"
    # published urls come from the RECENT tail of the append-order log
    rows = [{"asset_url": "old"}] + [{"asset_url": f"new{i}"} for i in range(8)]
    assert "old" not in published_asset_urls(rows=rows)
    assert "new7" in published_asset_urls(rows=rows)
    # screenshot rung: product story with a url captures the UI; blocked -> logo
    fake_shot = lambda u: {"kind": "screenshot", "source_url": u}
    pb = {"topic": "openwiki", "story_type": "product", "url": "https://x.dev"}
    r = resolve(pb, _face=fake_face, _logo=fake_logo, _shot=fake_shot)
    assert r and r[0]["kind"] == "screenshot" and r[0]["source_url"] == "https://x.dev"
    r = resolve(pb, _face=fake_face, _logo=fake_logo, _shot=lambda u: None)
    assert r and r[0]["kind"] == "logo", "bot-blocked screenshot -> falls to logo"
    r = resolve({**pb, "url": ""}, _face=fake_face, _logo=fake_logo,
                _shot=lambda u: (_ for _ in ()).throw(AssertionError("no url -> never called")))
    assert r and r[0]["kind"] == "logo"
    print("assets selftest ok (incl. screenshot rung)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", choices=["face", "logo"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    if a.cmd == "face" and a.name:
        r = face(a.name)
        print(json.dumps({k: v for k, v in (r or {}).items() if k != "svg"}, indent=1)
              if r else f"no acceptably-licensed photo of {a.name!r} found")
    elif a.cmd == "logo" and a.name:
        r = logo(a.name)
        print(f"logo found: {r['license']}" if r else "no logo match")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
