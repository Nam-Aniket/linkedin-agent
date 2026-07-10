#!/usr/bin/env python3
"""Multi-slide deck assembly: a tagged story -> a full 7-slide carousel PDF.

The content product, not just covers. One generated palette unifies EVERY slide
(including charts - CSS bars inherit the palette vars, so no more matplotlib warm-paper
clash). Reading-psychology is baked into the structure (sources: NN/g eye-tracking,
serial-position research):
  - PRIMACY/RECENCY: the strongest claim is slide 1 (cover), the payoff insight + CTA
    close the deck; the middle carries the low-text-load visual evidence (charts).
  - ONE IDEA PER SLIDE, <=2 text blocks (cognitive load - overloaded middles get skipped).
  - Z-PATTERN anchors on sparse slides: eyebrow top-left -> content mid-left ->
    footer bottom-left -> progress/swipe cue at the Z's exit (bottom-right).
  - CONTINUATION cues: "swipe" on the cover, "i / n" progress on inner slides
    (completion drive), nothing on the last slide.

Deck eval = deck_lint (structure, plain-language HARD gate, bait check, chart source)
+ per-slide browser layout lint + design_score metrics reported per slide.

  python3 html_deck.py            # renders the demo deck -> drafts/deck_* + deck.pdf
  python3 html_deck.py --selftest # deck_lint assertions, renders nothing
"""
import argparse
import html as _html
from pathlib import Path

import check
import design_score
import html_templates
from html_templates import SANS, SERIF, DISPLAY, _shell, _eyebrow, _esc
from render_covers import compose_best, HOOK_TEMPLATE, _story_seed
from palette_gen import palette_for
from render_html import render

DRAFTS = Path(__file__).parent / "drafts"
MIN_SLIDES, MAX_SLIDES = 6, 8
BAIT = ("comment below", "comment and", "follow for", "repost if", "dm me",
        "tag someone", "agree?", "thoughts?", "who else", "like if")


# --- inner-slide templates (cover comes from render_covers/html_templates) ----------
def s_context(pal, s):
    body = f"""<div class="stage">
  {_eyebrow(s.get('eyebrow', 'the setup'))}
  <div style="position:absolute; top:40%; left:0; right:0; transform:translateY(-50%);">
    <h1 class="headline" data-lint="text" style="font-family:{DISPLAY}; font-size:72px;
        max-width:92%; color:var(--ink);">{_esc(s['body'])}</h1>
  </div>
</div>"""
    return _shell(pal, body)


def s_insight(pal, s):
    body = f"""<div class="stage">
  {_eyebrow(s.get('eyebrow', 'the takeaway'))}
  <div style="position:absolute; top:40%; left:0; right:0; transform:translateY(-50%);">
    <h1 class="headline" data-lint="text" style="font-family:{DISPLAY}; font-size:72px;
        max-width:92%; color:var(--ink);">{_esc(s['body'])}</h1>
    <hr class="rule" style="width:180px; margin-top:48px;">
  </div>
</div>"""
    return _shell(pal, body)


def s_bignum(pal, s):
    body = f"""<div class="stage">
  {_eyebrow(s.get('eyebrow', 'the number'))}
  <div style="position:absolute; top:26%; left:0; right:0;">
    <div data-lint="text" style="font-family:{DISPLAY}; font-weight:800; font-size:300px;
         line-height:0.85; letter-spacing:-0.04em; color:var(--accent);">{_esc(s['number'])}</div>
    <p class="headline" data-lint="text" style="margin-top:44px; font-size:42px;
       max-width:80%; color:var(--ink);">{_esc(s['caption'])}</p>
  </div>
</div>"""
    return _shell(pal, body)


def s_chart(pal, s):
    """Ranked CSS bars - the chart INHERITS the deck palette (accent = the one highlight).
    Storytelling rules: declarative takeaway, ONE highlight, a visible source."""
    items = s["items"]
    vmax = max(i["value"] for i in items)
    fmt = s.get("value_fmt", "{:g}")
    rows = []
    for it in items:
        hot = it.get("highlight", False)
        w = max(4, round(100 * it["value"] / vmax))
        col = "var(--accent)" if hot else "var(--muted)"
        wt = 800 if hot else 400
        rows.append(f"""<div style="margin-bottom:44px;">
  <div data-lint="text" style="font-size:30px; font-weight:{wt}; color:var(--ink);
       margin-bottom:12px;">{_esc(it['label'])}</div>
  <div style="display:flex; align-items:center; gap:24px;">
    <div style="height:44px; width:{w * 0.82:.0f}%; background:{col}; border-radius:3px;"></div>
    <div data-lint="text" style="font-size:32px; font-weight:{wt};
         color:{col if hot else 'var(--muted)'};">{_esc(fmt.format(it['value']))}</div>
  </div>
</div>""")
    body = f"""<div class="stage">
  {_eyebrow(s.get('eyebrow', 'the evidence'))}
  <h1 class="headline" data-lint="text" style="font-family:{DISPLAY}; font-size:56px;
      margin-top:56px; max-width:94%; color:var(--ink);">{_esc(s['takeaway'])}</h1>
  <div style="margin-top:72px;">{''.join(rows)}</div>
  <div data-lint="text" style="position:absolute; bottom:16px; left:0; font-size:20px;
       color:var(--muted);">{_esc(s['source'])}</div>
</div>"""
    return _shell(pal, body)


def s_cta(pal, s):
    body = f"""<div class="stage">
  {_eyebrow(s.get('eyebrow', 'if this was useful'))}
  <div style="position:absolute; top:40%; left:0; right:0; transform:translateY(-50%);">
    <h1 class="headline" data-lint="text" style="font-family:{DISPLAY}; font-size:76px;
        max-width:90%; color:var(--ink);">{_esc(s['line'])}</h1>
    <p data-lint="text" style="margin-top:44px; font-size:34px; font-weight:700;
       color:var(--accent);">{_esc(s.get('mention', ''))}</p>
  </div>
</div>"""
    return _shell(pal, body)


def s_artifact(pal, s):
    """Real evidence on a slide: an image (screenshot/photo/chart file) or terminal
    output, in optional chrome, with a takeaway and - when the license demands it -
    a visible credit line. Fields: eyebrow, takeaway, credit?, and ONE of:
      image (path) [+ frame: browser|none, url_label, treatment: none|duotone|halftone]
      terminal (text) [+ title]"""
    if s.get("terminal") is not None:
        media = html_templates.terminal_frame(_html.escape(str(s["terminal"])),
                                              s.get("title", "terminal"))
    else:
        # unframed images taller than the 680px window get a focal-point cover-crop
        # (keep the subject, not blindly the top); framed screenshots keep the old
        # top-crop - for a web page the top IS the subject
        focal = None
        if s.get("frame") != "browser":
            from PIL import Image as _Im
            w, h = _Im.open(s["image"]).size
            stage_w = html_templates.FRAME_W - html_templates.LEFT - html_templates.RIGHT
            if h * stage_w / w > 680:
                focal = html_templates.focal_y(s["image"])
        img = html_templates.image_slot(
            s["image"], s.get("treatment", "none"),
            style="height:680px;" if focal is not None else "",
            dark=bool(pal.get("dark")), accent=pal["accent"], focal=focal)
        media = (html_templates.browser_frame(img, s.get("url_label", ""))
                 if s.get("frame") == "browser" else img)
    credit = html_templates.credit_line(s["credit"]) if s.get("credit") else ""
    body = f"""<style>{html_templates.MEDIA_CSS}</style>
<div class="stage">
  {_eyebrow(s.get('eyebrow', 'the evidence'))}
  <div style="margin-top:52px; max-height:680px; overflow:hidden;
       border-radius:14px;">{media}</div>
  <h1 class="headline" data-lint="text" style="font-family:{DISPLAY}; font-size:52px;
      margin-top:56px; max-width:92%; color:var(--ink);">{_esc(s['takeaway'])}</h1>
  <div style="position:absolute; bottom:16px; left:0;">{credit}</div>
</div>"""
    return _shell(pal, body)


SLIDES = {"context": s_context, "chart": s_chart, "bignum": s_bignum,
          "insight": s_insight, "cta": s_cta, "artifact": s_artifact}


# --- deck-level eval ------------------------------------------------------------------
def deck_lint(deck):
    """Structure + copy gates for the WHOLE deck. Empty list = passes."""
    f = []
    slides = deck.get("slides", [])
    n = len(slides)
    if not (MIN_SLIDES <= n <= MAX_SLIDES):
        f.append(f"{n} slides - keep {MIN_SLIDES}-{MAX_SLIDES}")
    if slides and slides[0].get("kind") != "cover":
        f.append("slide 1 must be the cover (primacy: strongest claim first)")
    if slides and slides[-1].get("kind") not in ("cta", "insight"):
        f.append("last slide must be insight/cta (recency: close on the payoff)")
    if slides and slides[0].get("asset") and not str(slides[0].get("headline", "")).strip():
        f.append("media cover (asset) needs a headline - the variant template is type+media")
    for i, s in enumerate(slides):
        k = s.get("kind")
        if k != "cover" and k not in SLIDES:
            f.append(f"slide {i}: unknown kind {k!r}")
            continue
        texts = " . ".join(str(s.get(x, "")) for x in
                           ("eyebrow", "headline", "body", "number", "caption",
                            "takeaway", "line", "mention", "pull") if s.get(x))
        for v in check.plain_language(texts):          # plain language: HARD on slides
            f.append(f"slide {i}: plain: {v}")
        body_txt = " . ".join(str(s.get(x, "")) for x in
                              ("headline", "body", "caption", "takeaway", "line") if s.get(x))
        for v in check.caps_check(body_txt):
            f.append(f"slide {i}: {v}")                # caps: HARD on body copy (eyebrows exempt)
        for v in check.ai_tells(body_txt):             # tricolon/reveal: HARD on body copy
            f.append(f"slide {i}: {v}")                # (pull microcopy exempt - it IS a teaser)
        if i == n - 1 and s.get("pull"):               # enumerate is 0-based: i==n-1 is the LAST slide
            f.append("last slide has a 'pull' - the deck should end at rest, not tease")
        if "—" in texts or "–" in texts:
            f.append(f"slide {i}: em/en dash - plain hyphen")
        # license gate (creative engine): external assets carry provenance, and
        # attribution-required licenses must show a visible credit line
        a = s.get("asset")
        if a is not None:
            # normalize: Wikimedia says "CC BY 4.0" (spaces), tests said "CC-BY-4.0"
            lic = str(a.get("license", "")).strip().upper().replace(" ", "-")
            if not lic or lic == "UNKNOWN":
                f.append(f"slide {i}: asset without license metadata (license gate)")
            elif lic.startswith("CC-BY") and not str(s.get("credit", "")).strip():
                f.append(f"slide {i}: {lic} asset needs a visible credit line")
        if k == "artifact" and not (s.get("image") or s.get("terminal") is not None):
            f.append(f"slide {i}: artifact slide needs an image or terminal content")
        if k == "chart":
            if not s.get("source"):
                f.append(f"slide {i}: chart has no source (honesty gate)")
            hi = sum(1 for it in s.get("items", []) if it.get("highlight"))
            if hi != 1:
                f.append(f"slide {i}: {hi} bars highlighted - exactly ONE")
        if k == "cta":
            low = (s.get("line", "") + " " + s.get("mention", "")).lower()
            for b in BAIT:
                if b in low:
                    f.append(f"cta has engagement-bait: {b!r}")
    return f


def _progress(html_str, i, n, last=False, pull=None):
    """Inner slides: the footer-right Z-exit slot carries the continuation device.
    A 'pull' (open-loop microcopy like 'the catch') beats a bare progress marker when
    the slide should tease the next one; otherwise 'i / n' feeds the completion drive.
    The last slide gets nothing - the deck ends at rest."""
    if last:
        cue = ""
    elif pull:
        cue = f"{_html.escape(str(pull))} &raquo;&nbsp;&nbsp;<span style=\"opacity:.55\">{i} / {n}</span>"
    else:
        cue = f"{i} / {n}"
    return html_str.replace('<span class="swipe">swipe &raquo;</span>',
                            f'<span class="swipe">{cue}</span>')


def render_deck(deck, outdir=DRAFTS, name="deck", ask=None):
    """Lint -> render each slide (browser lint on) -> score -> assemble the PDF.
    Also writes <name>.json - a manifest of the deck's design attributes, which
    post.py reads at publish time to auto-log the post into tracking.csv.

    A cover slide WITH an `asset` field takes the media path (creative engine):
    compose.py samples 3 composition variants, YOU pick from the contact
    strip (`ask` injectable for tests), winner + losers land in picks.csv, and
    the whole deck wears the asset's brand palette when it has one."""
    fails = deck_lint(deck)
    if fails:
        raise ValueError("deck failed lint:\n  - " + "\n  - ".join(fails))
    story = deck["story"]
    pal = palette_for(story["mood"], _story_seed(story))
    cover = deck["slides"][0]
    asset = cover.get("asset")
    if asset and asset.get("path"):
        import palette_gen
        pal = palette_gen.palette_from_asset(asset["path"], dark=pal["dark"]) or pal
    slides = deck["slides"]
    n = len(slides)
    pngs, cover_info = [], {}
    for i, s in enumerate(slides, 1):
        out = Path(outdir) / f"{name}_{i}.png"
        if s["kind"] == "cover" and asset:
            import shutil
            import compose
            spec, png = compose.pick_flow({**story, **s}, asset, pal,
                                          outdir=outdir, name=f"{name}_cover", ask=ask)
            shutil.copy(png, out)
            m, _ = design_score.score(out, profile="media")
            cover_info = {"archetype": "media", "element_kind": asset.get("kind", ""),
                          "placement": spec["placement"],
                          "composition": compose.signature(spec),
                          "asset_url": asset.get("source_url", ""),
                          "accent": pal["accent"], "palette_dark": int(pal["dark"]),
                          "scores": m}
        elif s["kind"] == "cover":
            # self-healing composer: renders the PNG itself, walking the placement
            # ladder until the browser lint + design gate pass (raw build dies on
            # seed luck when the element lands on a caption)
            arch, cpal, elkind, placed, m, cfails, tries = compose_best({**story, **s}, out)
            if cfails:
                raise ValueError("cover failed even after recompose: " + "; ".join(cfails))
            cover_info = {"archetype": arch, "element_kind": elkind, "placement": placed,
                          "accent": cpal["accent"], "palette_dark": int(cpal["dark"]),
                          "scores": m}
        else:
            html_str = _progress(SLIDES[s["kind"]](pal, s), i, n,
                                 last=(i == n), pull=s.get("pull"))
            render(html_str, out, check=True)
            m, _ = design_score.score(out)
        print(f"  slide {i} {s['kind']:8s} ws={m['whitespace']} bal={m['balance_y']} gl={m['glance']}")
        pngs.append(out)

    import json
    manifest = {**cover_info, "hook": story["hook"], "mood": story["mood"],
                "subject": story.get("subject", ""), "slides": n,
                "kinds": [s["kind"] for s in slides],
                "headlines": [str(s.get(k)) for s in slides
                              for k in ("caption", "body", "takeaway", "line") if s.get(k)],
                "sources": [s["source"] for s in slides if s.get("source")]}
    (Path(outdir) / f"{name}.json").write_text(json.dumps(manifest, indent=1))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg
    from matplotlib.backends.backend_pdf import PdfPages
    pdf_path = Path(outdir) / f"{name}.pdf"
    with PdfPages(pdf_path) as pdf:
        for p in pngs:
            # 15x18.75in @ 72dpi = a 1080x1350 POINT page carrying the 1080x1350px
            # PNG 1:1 (no resampling). LinkedIn's doc viewer sizes from physical
            # page dims - the old 10.8in page rendered small in the feed.
            fig = plt.figure(figsize=(15, 18.75), dpi=72)
            ax = fig.add_axes([0, 0, 1, 1])
            ax.axis("off")
            ax.imshow(mpimg.imread(p))
            pdf.savefig(fig)
            plt.close(fig)
    return pdf_path, pngs


# --- demo deck (PLACEHOLDER numbers - real posts use sourced data) --------------------
DEMO = {
    "story": {"hook": "stat", "mood": "urgency", "subject": "AI agent reliability",
              "keywords": ["agent", "reliability", "cost"]},
    "slides": [
        {"kind": "cover", "eyebrow": "AI reliability", "number": "70%",
         "caption": "of AI agent runs miss a multi-step task on the first try"},
        {"kind": "context", "eyebrow": "the setup", "pull": "the numbers",
         "body": "Everyone ships agents. Almost nobody measures how often they finish the job."},
        {"kind": "chart", "eyebrow": "the evidence",
         "takeaway": "Most runs need a retry, and retries are the real bill",
         "source": "source: illustrative demo values",
         "value_fmt": "{:g}%",
         "items": [{"label": "finish first try", "value": 30},
                   {"label": "finish after retries", "value": 45, "highlight": True},
                   {"label": "never finish", "value": 25}]},
        {"kind": "bignum", "eyebrow": "the hidden cost", "number": "2.4x", "pull": "so what",
         "caption": "what a retried run costs vs a clean one"},
        {"kind": "insight", "eyebrow": "the takeaway",
         "body": "Reliability is a cost problem. Every retry is a bill you did not plan."},
        {"kind": "cta", "eyebrow": "do this next",
         "line": "Measure your finish rate before you scale the fleet.",
         "mention": "link in comments"},
    ],
}


def _selftest():
    assert deck_lint(DEMO) == [], deck_lint(DEMO)
    bad = {**DEMO, "slides": DEMO["slides"][:3]}
    assert any("slides" in x for x in deck_lint(bad)), "short deck must fail"
    nosrc = {**DEMO, "slides": [dict(s, source="") if s["kind"] == "chart" else s
                                for s in DEMO["slides"]]}
    assert any("source" in x for x in deck_lint(nosrc))
    jargon = {**DEMO, "slides": [dict(DEMO["slides"][1], body="We optimize inference throughput.")]
              + DEMO["slides"][1:]}
    assert any("plain" in x for x in deck_lint(jargon)), "jargon must fail the plain gate"
    baity = {**DEMO, "slides": DEMO["slides"][:-1] +
             [dict(DEMO["slides"][-1], line="Comment below and I will DM you the guide")]}
    assert any("bait" in x for x in deck_lint(baity))
    shouty = {**DEMO, "slides": [dict(DEMO["slides"][1],
              body="EVERYONE SHIPS AGENTS AND NOBODY MEASURES ANYTHING")] + DEMO["slides"][1:]}
    assert any("all-caps" in x for x in deck_lint(shouty)), "caps gate must fire on slides"
    tease_end = {**DEMO, "slides": DEMO["slides"][:-1] +
                 [dict(DEMO["slides"][-1], pull="wait for it")]}
    assert any("end at rest" in x for x in deck_lint(tease_end)), "last-slide pull must fail"
    # license gate: unknown license blocks; CC-BY without credit blocks; credit passes;
    # CC0/own need no credit
    art = {"kind": "artifact", "eyebrow": "the evidence", "image": "x.png",
           "takeaway": "A real screenshot beats a claim."}
    def with_art(s):
        return {**DEMO, "slides": [DEMO["slides"][0], s] + DEMO["slides"][2:]}
    assert any("license metadata" in x for x in deck_lint(with_art({**art, "asset": {}})))
    ccby = {**art, "asset": {"license": "CC-BY-4.0", "attribution": "Photo: J. Doe"}}
    assert any("credit line" in x for x in deck_lint(with_art(ccby)))
    # the REAL Wikimedia spelling (spaces) must also demand a credit
    wiki = {**art, "asset": {"license": "CC BY 4.0", "attribution": "L. Kobus"}}
    assert any("credit line" in x for x in deck_lint(with_art(wiki))), \
        "space-form CC BY must be caught (real Wikimedia string)"
    assert not [x for x in deck_lint(with_art({**ccby, "credit": "Photo: J. Doe (CC BY 4.0)"}))
                if "credit" in x or "license" in x]
    assert not [x for x in deck_lint(with_art({**art, "asset": {"license": "CC0"}}))
                if "credit" in x or "license" in x]
    assert any("image or terminal" in x for x in deck_lint(with_art(
        {"kind": "artifact", "takeaway": "empty artifact must fail"})))
    # media cover: an asset without a headline fails; with one (+ license) passes
    media_cover = {**DEMO, "slides": [dict(DEMO["slides"][0],
                   asset={"kind": "logo", "license": "CC0"})] + DEMO["slides"][1:]}
    assert any("needs a headline" in x for x in deck_lint(media_cover))
    media_ok = {**DEMO, "slides": [dict(DEMO["slides"][0], headline="A real headline",
                asset={"kind": "logo", "license": "CC0"})] + DEMO["slides"][1:]}
    assert not any("headline" in x for x in deck_lint(media_ok)), deck_lint(media_ok)
    # media toolkit shapes (offline)
    import tempfile
    from PIL import Image as _Im
    tp = Path(tempfile.mkdtemp()) / "t.png"
    _Im.new("RGB", (4, 4), "red").save(tp)
    assert html_templates.image_slot(tp).startswith('<div class=""')
    assert 'data:image/png;base64,' in html_templates.image_slot(tp)
    assert 'duo-wrap' in html_templates.image_slot(tp, "duotone")
    assert 'news.ycombinator.com' in html_templates.browser_frame("<b>x</b>",
                                                                  "news.ycombinator.com")
    assert 'data-credit' in html_templates.credit_line("Photo: J. Doe (CC BY)")
    assert "&lt;" in html_templates.credit_line("<script>")   # credit is escaped
    # chunk 6: focal-point crop finds the detail band; duo-dark fires only on dark
    import numpy as _np
    top = _np.zeros((200, 200, 3), _np.uint8)
    top[20:60] = _np.random.default_rng(0).integers(0, 255, (40, 200, 3))
    fp = tp.parent / "focal.png"
    _Im.fromarray(top).save(fp)
    assert html_templates.focal_y(fp) < 35, "detail near the top -> focal near the top"
    duo = html_templates.image_slot(fp, "duotone", dark=True, accent="#6688ff", focal=40)
    assert "duo-dark" in duo and "--duo-rot" in duo and "object-position:center 40%" in duo
    assert "duo-dark" not in html_templates.image_slot(fp, "duotone", accent="#6688ff")
    print("html_deck selftest ok - structure, source, plain, bait, caps, pull, license "
          "and media gates all fire")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    DRAFTS.mkdir(exist_ok=True)
    pdf, pngs = render_deck(DEMO)
    print(f"wrote {pdf} ({len(pngs)} pages)")


if __name__ == "__main__":
    main()
