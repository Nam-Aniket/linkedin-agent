#!/usr/bin/env python3
"""compose.py - composition GRAMMAR + seeded sampler (creative engine, chunk 4).

Instead of fixed cover templates, composition is a point in a small grammar:

  placement   left | right | full-bleed | circle-cut | lower-third
  scale       dominant | half | chip
  treatment   duotone | halftone | frame | none          (photos; svg logos skip)
  background  flat | gradient | motif

One parametric template renders any valid point. A seeded RNG samples variants,
so the same story always yields the same candidates on any machine, any model.
Two gates keep it honest:
  - variants must differ from EACH OTHER on >= 2 axes (no near-duplicates)
  - DESIGN-NOVELTY: a candidate must differ from the last N published
    compositions (tracking.csv `composition` signatures) on >= 2 axes -
    the visual twin of the copy-novelty gate.

LOCKED (never sampled): stage grid + margins, the profile display face, footer
signature, one accent, mutedness. NOTE: this family puts the eyebrow TOP-RIGHT -
LinkedIn's "title - N pages" chip overlays the top-left corner in the feed
(observed on the live 2026-07-08 post), so nothing load-bearing lives there.

Deviation from spec, on purpose: `text relation` is DERIVED from placement
(full-bleed -> overlay on a scrim, chip -> wrap, else split) instead of being a
free axis - sampling it independently mostly produced invalid pairs. And
`cutout` became `frame` (chunk-1 chrome) - true cutouts need segmentation,
which would break the no-model rule.

  python3 compose.py --selftest            # offline: grammar, determinism, gates
  python3 compose.py --demo                # live: 3 variants for a demo story
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

import element as element_mod
import html_templates
import tracker
from html_templates import DISPLAY, SANS, AUTHOR, _esc

DRAFTS = Path(__file__).parent / "drafts"
W, H = 1080, 1350

AXES = {
    "placement": ("left", "right", "full-bleed", "circle-cut", "lower-third",
                  "banner"),
    "scale": ("dominant", "half", "chip"),
    "treatment": ("duotone", "halftone", "frame", "none"),
    "background": ("flat", "gradient", "motif"),
}
# Perceptual weights (2026-07-10, born from a real miss: two banner|dominant
# covers on consecutive days passed the old equal-weight gate because the two
# axes that differed - treatment, background - are the two the eye barely
# registers). placement and scale decide where the media sits and how big;
# they weigh double. mood = dark vs light ground, read from tracking.csv's
# palette_dark; it was recorded but never gated.
WEIGHTS = {"placement": 2, "scale": 2, "treatment": 1, "background": 1,
           "mood": 1}
MIN_APART = 3               # weighted; quiet axes alone (1+1) can never clear it
HISTORY_N = 8               # how many recent posts the novelty gate looks back


def valid(spec):
    """Grammar constraints - combinations that cannot render sanely."""
    if spec["placement"] == "full-bleed" and spec["scale"] != "dominant":
        return False                      # a full-bleed chip is not a thing
    if spec["placement"] == "circle-cut" and spec["treatment"] == "frame":
        return False                      # chrome inside a circle clips badly
    if spec["placement"] == "banner" and spec["scale"] != "dominant":
        return False                      # banner IS the full uncropped image
    return True


def distance(a, b):
    """Perceptual distance: summed WEIGHTS of the axes two compositions differ
    on. mood compares like any axis; a spec that doesn't carry mood (old rows,
    bare samples) mismatches everything - errs lenient, unknown never blocks."""
    return sum(w for k, w in WEIGHTS.items() if a.get(k) != b.get(k))


def signature(spec):
    return "|".join(spec[k] for k in AXES)


def parse_signature(sig):
    parts = (sig or "").split("|")
    return dict(zip(AXES, parts)) if len(parts) == len(AXES) else None


def published_signatures(rows=None):
    """Composition signatures of the last HISTORY_N published posts.
    tracking.csv appends, so the RECENT posts are the tail, not the head."""
    rows = tracker._read() if rows is None else rows
    sigs = []
    for r in rows[-HISTORY_N:]:
        s = parse_signature(r.get("composition", ""))
        if s:
            pd = str(r.get("palette_dark", "")).strip()
            if pd in ("0", "1"):        # unknown mood stays absent (lenient)
                s["mood"] = "dark" if pd == "1" else "light"
            sigs.append(s)
    return sigs


def sample_variants(story, n=3, history=None, tries=400, fixed=None, taste=None,
                    min_apart=MIN_APART):
    """Deterministically sample n compositions: valid, >= min_apart weighted
    distance from each other and from recent published history. Same story ->
    same variants. `fixed` pins axes (e.g. treatment='none' for logo assets,
    where photo treatments are visual no-ops and would waste variant distance);
    non-AXES keys in fixed (mood) ride along into the distance checks.
    `taste` = tracker.taste_weights() output: once ~20 picks exist, axis values
    YOU keep choosing get proposed more often (weighted, never exclusive -
    the novelty gates still force variety). Same story + same taste data = same
    variants, on any machine, any model.
    `min_apart` below MIN_APART is a DELIBERATE repeat - a human call, never a
    default; compose_variants prints when the gate starves so the choice is
    informed, not silent."""
    seed = int(hashlib.md5(str(story.get("subject", "")).encode()).hexdigest(), 16)
    rng = random.Random(seed)
    hist = published_signatures() if history is None else history
    out = []
    for _ in range(tries):
        spec = {k: (rng.choices(v, [taste[k].get(x, 0.5) for x in v])[0]
                    if taste and k in taste else rng.choice(v))
                for k, v in AXES.items()}
        spec.update(fixed or {})
        if not valid(spec):
            continue
        if any(distance(spec, o) < min_apart for o in out):
            continue
        if any(distance(spec, h) < min_apart for h in hist):
            continue
        out.append(spec)
        if len(out) == n:
            break
    return out


# --- the parametric media-cover template -------------------------------------------

def _media_html(asset, spec, pal):
    """The hero media element. Three classes, treated differently on purpose:
    - svg logo: colorless mark, wears the accent, centered
    - logo-img (kind contains 'logo'): a BRAND's colors ARE the content - never
      duotoned/halftoned (grayscale kills the identity), always centered
    - photo/screenshot: fills its panel, treatments apply"""
    if asset.get("svg"):
        return (f'<div style="width:100%;height:100%;display:flex;align-items:center;'
                f'justify-content:center;color:{pal["accent"]};">'
                f'<div style="width:62%;">{asset["svg"]}</div></div>')
    if "logo" in str(asset.get("kind", "")) or "logo" in str(asset.get("name", "")).lower():
        return (f'<div style="width:100%;height:100%;display:flex;align-items:center;'
                f'justify-content:center;">'
                f'<img src="{html_templates.img_data_uri(asset["path"])}" '
                f'style="width:72%;display:block;"></div>')
    uncropped = spec["placement"] == "banner"
    img = html_templates.image_slot(asset["path"], spec["treatment"]
                                    if spec["treatment"] in ("duotone", "halftone")
                                    else "none",
                                    style="" if uncropped else "height:100%;",
                                    dark=bool(pal.get("dark")), accent=pal["accent"],
                                    focal=None if uncropped else
                                    html_templates.focal_y(asset["path"]))
    if spec["treatment"] == "frame":
        img = html_templates.browser_frame(img, asset.get("source_label", ""))
    return img


def _background(spec, pal, subject):
    if spec["background"] == "gradient":
        # the alpha stop MUST sit on an opaque ground layer - alone, it
        # composites against the white page body (measured: 13% slate came out
        # near-white, 233 vs the expected ~35)
        return (f"background: radial-gradient(120% 90% at 20% 10%, "
                f"{pal['muted']}22 0%, transparent 55%), {pal['ground']};")
    if spec["background"] == "motif":
        return f"background: {pal['ground']};"      # motif svg layered separately
    return f"background: {pal['ground']};"


def _motif_layer(spec, pal, subject):
    if spec["background"] != "motif":
        return ""
    el = element_mod.element({"subject": subject, "keywords": [subject]})
    return (f'<div style="position:absolute; right:-140px; bottom:-140px; width:640px; '
            f'height:640px; opacity:0.10; color:{pal["accent"]};">{el["svg"]}</div>')


# per-placement geometry: (media css, text css, media height for images)
_GEOM = {
    "left":        ("position:absolute; left:0; top:0; bottom:0; width:46%;"
                    " overflow:hidden;",
                    "position:absolute; left:50%; right:84px; top:22%;"),
    "right":       ("position:absolute; right:0; top:0; bottom:0; width:46%;"
                    " overflow:hidden;",
                    "position:absolute; left:84px; width:44%; top:22%;"),
    "full-bleed":  ("position:absolute; inset:0; overflow:hidden;",
                    "position:absolute; left:84px; right:84px; bottom:180px;"),
    "circle-cut":  ("position:absolute; right:64px; top:150px; width:560px;"
                    " height:560px; border-radius:50%; overflow:hidden;",
                    "position:absolute; left:84px; right:84px; bottom:180px;"),
    "lower-third": ("position:absolute; left:0; right:0; bottom:0; height:38%;"
                    " overflow:hidden;",
                    "position:absolute; left:84px; right:84px; top:150px;"),
    # banner: the media at its NATURAL aspect, uncropped (UI screenshots must
    # not be cover-cropped - the interface is the content). Text below.
    # ponytail: assumes media aspect >= ~0.8 (landscape/square-ish); a tall
    # portrait asset will collide with the text zone and the lint will drop it.
    "banner":      ("position:absolute; left:6%; right:6%; top:48px;",
                    "position:absolute; left:84px; right:84px; bottom:130px;"),
}
_SCALE_SHRINK = {"dominant": 1.0, "half": 0.62, "chip": 0.34}


def render_variant_html(story, asset, pal, spec):
    """One composition spec -> full cover HTML (deterministic)."""
    media_css, text_css = _GEOM[spec["placement"]]
    shrink = _SCALE_SHRINK[spec["scale"]]
    if spec["placement"] != "full-bleed" and shrink < 1.0:
        media_css += f" transform: scale({shrink}); transform-origin: top right;"
    overlay = spec["placement"] == "full-bleed"
    scrim = (f'<div style="position:absolute; inset:0; background:linear-gradient('
             f'180deg, transparent 35%, {pal["ground"]}F2 78%);"></div>') if overlay else ""
    credit = (html_templates.credit_line(story["credit"])
              if story.get("credit") else "")
    # banner puts media in the top-right, where the eyebrow normally sits - it would
    # print straight over the image. Under banner the eyebrow leads the text block.
    banner_eyebrow = spec["placement"] == "banner"
    _eb_pos = ("position:static; margin:0 0 22px; text-align:left;" if banner_eyebrow
               else "position:absolute; right:84px; top:64px; margin:0;"
                    " display:inline-block;")
    eyebrow_html = (f'<p data-lint="text" style="{_eb_pos} font-size:20px;'
                    f' font-weight:700; letter-spacing:0.22em; text-transform:uppercase;'
                    f' color:{pal["muted"]};">{_esc(story.get("eyebrow", ""))}</p>')
    return f"""<div class="root" style="all:initial; display:block; position:relative;
    width:{W}px; height:{H}px; overflow:hidden; {_background(spec, pal, story.get('subject',''))}
    font-family:{SANS}; color:{pal['ink']};">
  <style>{html_templates.MEDIA_CSS}
    .headline {{ font-family:{DISPLAY}; font-weight:800; letter-spacing:-0.01em;
                line-height:1.02; margin:0; color:{pal['ink']}; }}
  </style>
  {_motif_layer(spec, pal, story.get('subject', ''))}
  <div style="{media_css}">{_media_html(asset, spec, pal)}</div>
  {scrim}
  {'' if banner_eyebrow else eyebrow_html}
  <div style="{text_css}">
    {eyebrow_html if banner_eyebrow else ''}
    {story.get('logo_html', '')}
    <h1 class="headline" data-lint="text" style="font-size:{74 if overlay
        or spec['placement'] == 'banner' else 84}px;">
      {_esc(story['headline'])}</h1>
    <div style="height:8px; width:170px; background:{pal['accent']};
         border-radius:2px; margin-top:36px;"></div>
  </div>
  <div style="position:absolute; left:84px; right:84px; bottom:56px; display:flex;
       justify-content:space-between; align-items:baseline; font-family:{SANS};
       font-size:20px; color:{pal['muted']};">
    <span>{_esc(AUTHOR)} {('&nbsp;&middot;&nbsp; ' + credit) if credit else ''}</span>
    <span style="color:{pal['accent']}; font-weight:700;">{story.get('cta', 'swipe &raquo;')}</span>
  </div>
</div>"""


def compose_variants(story, asset, pal, outdir=DRAFTS, name="variant", n=3,
                     fixed=None, min_apart=MIN_APART):
    """Sample -> render -> heal: lint-failing samples are dropped and replaced by
    the next grammar point. Returns [(spec, png_path)] of gate-passing variants.
    `fixed` pins grammar axes (e.g. UI screenshots pin treatment - duotone or
    halftone would erase the interface the post is about).
    `min_apart` below MIN_APART = a deliberate, human-approved repeat (pinned
    stories can make novelty unsatisfiable - e.g. two wide-screenshot posts in
    a row both force banner|dominant). The gate starving is the signal to swap
    the story or the asset, not to quietly lower the bar."""
    from render_html import render
    import design_score
    hist = published_signatures()
    logoish = bool(asset.get("svg")) or "logo" in str(asset.get("kind", "")) \
        or "logo" in str(asset.get("name", "")).lower()
    fixed = dict(fixed) if fixed is not None else \
        ({"treatment": "none"} if logoish else {})
    # mood rides along so candidates face history on the same axes the gate reads
    fixed["mood"] = "dark" if pal.get("dark") else "light"
    candidates = sample_variants(story, n=max(n * 6, 18), history=hist,
                                 fixed=fixed, taste=tracker.taste_weights(),
                                 min_apart=min_apart)
    kept = []
    for spec in candidates:
        if len(kept) == n:
            break
        if logoish and spec["scale"] == "chip":
            continue        # a chip-sized logo floats in dead space - photos only
        out = Path(outdir) / f"{name}_{signature(spec).replace('|', '_')}.png"
        try:
            render(render_variant_html(story, asset, pal, spec), out, check=True)
            m, fails = design_score.score(out, profile="media")
        except RuntimeError as e:          # collision: drop, next grammar point
            print(f"  [drop] {signature(spec)}: browser lint ({str(e)[-60:].strip()})")
            continue
        if fails:
            print(f"  [drop] {signature(spec)}: design_score {fails}")
            continue
        if any(distance(spec, k) < min_apart for k, _ in kept):
            print(f"  [drop] {signature(spec)}: too close to a kept variant")
            continue
        # sidecar manifest: post.py --image reads this so tracking.csv gets
        # composition/asset_url without the deck-manifest path
        out.with_suffix(".json").write_text(json.dumps(
            {"composition": signature(spec), "asset_url": asset.get("source_url", ""),
             "accent": pal.get("accent", ""),
             "palette_dark": int(bool(pal.get("dark"))), "scores": m}, indent=1))
        kept.append((spec, out))
    if len(kept) < n:
        print(f"  [note] only {len(kept)}/{n} variants survived the gates")
    if not candidates:
        print(f"  [blocked] novelty gate: pinned axes {sorted(fixed)} + the last "
              f"{HISTORY_N} published posts leave no composition >= {min_apart} "
              f"apart. Swap the story/asset for feed contrast, or pass a lower "
              f"min_apart as an explicit, deliberate repeat.")
    return kept


# --- the pick flow (chunk 5): 3 variants -> contact strip -> you pick ---------------

def contact_strip(kept, out):
    """The gate-passing variants side by side in ONE numbered PNG - open it,
    pick a number. Pure PIL, no browser round-trip."""
    from PIL import Image, ImageDraw, ImageFont
    thumbs = [Image.open(p) for _, p in kept]
    th = 620
    thumbs = [t.resize((int(t.width * th / t.height), th)) for t in thumbs]
    gap = 24
    strip = Image.new("RGB", (sum(t.width for t in thumbs) + gap * (len(thumbs) + 1),
                              th + 2 * gap), "#202126")
    d = ImageDraw.Draw(strip)
    font = ImageFont.load_default(44)
    x = gap
    for i, t in enumerate(thumbs):
        strip.paste(t, (x, gap))
        d.ellipse((x + 14, gap + 14, x + 74, gap + 74), fill="#202126")
        d.text((x + 44, gap + 42), str(i + 1), fill="white", font=font, anchor="mm")
        x += t.width + gap
    strip.save(out)
    return out


def pick_flow(story, asset, pal, outdir=DRAFTS, name="variant", n=3, ask=None,
              picks_path=None):
    """Render n variants, show the contact strip, take the pick, log winner AND
    losers to picks.csv (the taste loop). Returns (spec, png) of the winner.
    `ask(kept, strip_path) -> index` is injectable; default = terminal input."""
    kept = compose_variants(story, asset, pal, outdir=outdir, name=name, n=n)
    if not kept:
        raise RuntimeError("no variant survived the gates - loosen or recalibrate")
    strip = contact_strip(kept, Path(outdir) / f"{name}_contact.png")
    print(f"  contact strip: {strip}")
    for i, (spec, p) in enumerate(kept, 1):
        print(f"    {i}. {signature(spec)}")
    if len(kept) == 1:
        idx = 0
        print("  only one survivor - auto-picked (still logged as a pick)")
    elif ask:
        idx = ask(kept, strip)
    else:
        while True:
            raw = input(f"  pick 1-{len(kept)}: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(kept):
                idx = int(raw) - 1
                break
    tracker.log_pick(story.get("subject", ""), [s for s, _ in kept], idx,
                     path=picks_path or tracker.PICKS)
    return kept[idx]


def _selftest():
    story = {"subject": "gemini test", "headline": "A test headline",
             "eyebrow": "the test"}
    # determinism: same story -> identical variant sets
    a = sample_variants(story, history=[])
    b = sample_variants(story, history=[])
    assert a == b and len(a) == 3, "sampler must be deterministic"
    # variants are mutually distinct (weighted) and all grammar-valid
    for i, s in enumerate(a):
        assert valid(s)
        for t in a[i + 1:]:
            assert distance(s, t) >= MIN_APART, (s, t)
    # grammar constraints hold
    assert not valid({"placement": "full-bleed", "scale": "chip",
                      "treatment": "none", "background": "flat"})
    # weighted distance: loud axes count double, quiet axes alone never clear
    s0 = dict(zip(AXES, ("left", "dominant", "duotone", "flat")))
    assert distance(s0, s0) == 0 and distance(s0, {**s0, "scale": "chip"}) == 2
    quiet = {**s0, "treatment": "frame", "background": "motif"}
    assert distance(s0, quiet) == 2 < MIN_APART, \
        "the 2026-07-10 repeat: quiet-axes-only must NOT clear the gate"
    assert distance(s0, {**s0, "placement": "banner", "background": "motif"}) == 3
    # mood is a gated axis; unknown mood is lenient (counts as different)
    assert distance({**s0, "mood": "dark"}, {**s0, "mood": "light"}) == 1
    assert distance({**s0, "mood": "dark"}, s0) == 1
    # signature stays 4-axis (mood lives in palette_dark, not the string)
    assert parse_signature(signature({**s0, "mood": "dark"})) == s0
    assert parse_signature("bad") is None and parse_signature("") is None
    # DESIGN-NOVELTY gate: history repels the space around each published post
    near = {**a[0]}
    hist = [near]
    c = sample_variants(story, history=hist)
    for s in c:
        assert distance(s, near) >= MIN_APART, "history must repel samples"
    # published_signatures reads the tracker column (tolerates missing/blank)
    # and attaches mood from palette_dark when the row has it
    rows = [{"composition": signature(s0)}, {"composition": ""}, {}]
    assert published_signatures(rows) == [s0]
    moody = published_signatures([{"composition": signature(s0),
                                   "palette_dark": "1"}])
    assert moody == [{**s0, "mood": "dark"}]
    # ...and reads the RECENT tail, not the oldest head (append-order file)
    old = {**s0, "placement": "right"}
    many = [{"composition": signature(old)}] + \
        [{"composition": signature(s0)}] * HISTORY_N
    assert old not in published_signatures(many), "gate must look at the newest N"
    # fixed axes pin (logo assets: treatment is a no-op, don't sample it)
    fx = sample_variants(story, history=[], fixed={"treatment": "none"})
    assert fx and all(s["treatment"] == "none" for s in fx)
    for i, s in enumerate(fx):
        for t in fx[i + 1:]:
            assert distance(s, t) >= MIN_APART   # still apart on OTHER axes
    # taste weighting: deterministic, and a strong preference shifts what gets sampled
    taste = {"placement": {"circle-cut": 0.98, "left": 0.02, "right": 0.02,
                           "full-bleed": 0.02, "lower-third": 0.02,
                           "banner": 0.02}}
    t1 = sample_variants(story, history=[], taste=taste)
    t2 = sample_variants(story, history=[], taste=taste)
    assert t1 == t2, "taste-weighted sampling must stay deterministic"
    n_cc = sum(1 for s in t1 if s["placement"] == "circle-cut")
    n_cc_plain = sum(1 for s in a if s["placement"] == "circle-cut")
    assert n_cc >= max(1, n_cc_plain), (n_cc, n_cc_plain)
    # ...but taste never overrides the gates: variants stay >=2 axes apart
    for i, s in enumerate(t1):
        for t in t1[i + 1:]:
            assert distance(s, t) >= MIN_APART
    # contact strip: n numbered thumbnails -> one PNG wider than each input
    import tempfile
    from PIL import Image
    d = Path(tempfile.mkdtemp())
    fake = []
    for i, col in enumerate(("#803030", "#308030", "#303080")):
        p = d / f"v{i}.png"
        Image.new("RGB", (216, 270), col).save(p)
        fake.append(({k: AXES[k][0] for k in AXES}, p))
    strip = contact_strip(fake, d / "strip.png")
    w, h = Image.open(strip).size
    assert w > 3 * 216 * 620 / 270 and h > 620, (w, h)

    # banner media occupies the top-right, so the eyebrow must NOT be pinned there
    # (it printed over the table header on the open-code-review cover, 2026-07-10).
    story = {"subject": "s", "eyebrow": "EYEBROW", "headline": "H"}
    pal = {"ground": "#111", "ink": "#eee", "muted": "#888", "accent": "#0f0"}
    asset = {"kind": "photo", "name": "a", "path": str(fake[0][1])}
    base = {"scale": "dominant", "treatment": "none", "background": "flat"}
    banner = render_variant_html(story, asset, pal, {**base, "placement": "banner"})
    left = render_variant_html(story, asset, pal, {**base, "placement": "left"})
    assert "top:64px" in left.split("EYEBROW")[0].rsplit("<p", 1)[-1], "left eyebrow moved"
    assert "top:64px" not in banner.split("EYEBROW")[0].rsplit("<p", 1)[-1], \
        "banner eyebrow is still pinned over the media"
    print("compose selftest ok (incl. taste weighting + contact strip + banner eyebrow)")


def _demo(pick=False):
    import assets
    import palette_gen
    a = assets.wikimedia_photo("Google Gemini logo", portrait=False)
    pal = palette_gen.palette_from_asset(a["path"], dark=True) or \
        palette_gen.palette_for("bold", 2)
    story = {"subject": "Google Gemini", "eyebrow": "model economics",
             "headline": "Gemini is winning a race nobody priced.",
             "credit": f"Logo: {a['license']}, Wikimedia Commons"}
    if pick:
        spec, path = pick_flow(story, a, pal, name="_demo_variant")
        print(f"picked: {signature(spec)} -> {path}")
        return
    kept = compose_variants(story, a, pal, name="_demo_variant")
    for spec, path in kept:
        print(signature(spec), "->", path)
    print(f"{len(kept)} gate-passing variants")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--pick", action="store_true",
                    help="with --demo: interactive 3-variant pick (logs to picks.csv)")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    elif a.demo:
        _demo(pick=a.pick)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
