#!/usr/bin/env python3
"""HTML/CSS cover templates — one function per archetype, each a full 1080x1350 page.

Each function takes (palette, story) and returns a complete HTML page whose root sets
the four CSS custom properties (--ground/--ink/--muted/--accent) from the palette and
paints the ground. The layout is a left-aligned grid on safe margins
(sides ~8.5%, footer lifted above LinkedIn's mobile-UI overlap zone).

FONT STRATEGY (all three faces come from profile.json design.fonts):
  - DISPLAY (headlines + hero numerals): YOUR display face, vendored as a TTF under
    elements/fonts/ and bundled as a base64 @font-face so headless Chromium always
    has it. Not configured = system sans (renders fine, no display voice yet).
  - Body/small text (eyebrow, footer, captions' siblings, list rows): the SANS stack.
    Display faces are usually too heavy below display sizes.
  - Display SERIF: used deliberately for the question archetype (big italic serif "?"
    + serif headline). Default Georgia ships with the browser, zero page weight.

Design rules honored: low-saturation ground, high-contrast ink, ONE saturated accent
(<=10% of the frame), muted secondary text, NO boxy borders/containers (elements float on
the ground), generous whitespace. The saturation knobs live in profile.json.

Integration contract: every template includes an EMPTY, hidden-by-default
`<div class="element-slot"></div>` placed sensibly (upper-right, beside the hero). The
element layer (built by another agent) fills it later. Text that must not clip/overlap is
tagged `data-lint="text"` so render_html.py's browser lint can check it.

  python3 html_templates.py   # writes drafts/_tmpl_*.png for each archetype (needs render_html)
"""
import base64
import html as _html
from pathlib import Path

import config as _profile

AUTHOR = _profile.P["author"]          # the footer signature on every slide

# Single-quoted family names so these are safe inside BOTH double-quoted inline
# style="..." attributes and <style> blocks. (Double quotes here would truncate any
# inline style attribute at the first inner ".)
_FONTS = _profile.P["design"]["fonts"]
SANS = _FONTS["sans"]
SERIF = _FONTS["serif"]

# DISPLAY face for headlines + hero numerals - YOUR pick (onboarding step 4 sets
# design.fonts.display_name + display_file in profile.json; drop the TTF under
# elements/fonts/). Bundled as a base64 @font-face so headless Chromium always
# has it. No font configured (or file missing) = system sans headlines: it still
# renders, it just won't have a distinctive display voice yet.
_DISPLAY_TTF = (Path(__file__).parent / _FONTS["display_file"]
                if _FONTS.get("display_file") else None)
if _FONTS.get("display_name") and _DISPLAY_TTF and _DISPLAY_TTF.exists():
    DISPLAY = f"'{_FONTS['display_name']}', " + SANS
    _FONT_FACE = (f"@font-face {{ font-family: '{_FONTS['display_name']}'; "
                  "src: url(data:font/ttf;base64,"
                  + base64.b64encode(_DISPLAY_TTF.read_bytes()).decode()
                  + ") format('truetype'); }")
else:
    DISPLAY = SANS
    _FONT_FACE = ""

# Grid, in px on the 1080x1350 frame (LinkedIn's 4:5 feed canvas).
FRAME_W, FRAME_H = 1080, 1350
LEFT = 92          # ~8.5%
RIGHT = 92
TOP = 96
FOOT = 92          # footer baseline area, lifted clear of the mobile-UI overlap


def _esc(s):
    return _html.escape(str(s))


def _shell(palette, body, *, serif_body=False, cta="swipe &raquo;"):
    """Wrap archetype `body` HTML in the full page: root vars + ground + grid + footer.

    `body` is the archetype-specific content placed inside `.stage` (the safe-margin
    canvas). The eyebrow, footer and element-slot are added by the caller via `body`
    so each archetype controls placement, but the shell owns the frame + vars.
    """
    p = palette
    base_font = SERIF if serif_body else SANS
    return f"""<div class="root">
<style>
  {_FONT_FACE}
  .root {{
    --ground: {p['ground']};
    --ink: {p['ink']};
    --muted: {p['muted']};
    --accent: {p['accent']};
    all: initial;
    display: block;
    width: {FRAME_W}px; height: {FRAME_H}px;
    background: var(--ground);
    color: var(--ink);
    font-family: {base_font};
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    overflow: hidden;
    position: relative;
    box-sizing: border-box;
  }}
  .root *, .root *::before, .root *::after {{ box-sizing: border-box; }}
  .stage {{
    position: absolute;
    left: {LEFT}px; right: {RIGHT}px; top: {TOP}px; bottom: {FOOT}px;
  }}
  .eyebrow {{
    font-family: {SANS};
    font-size: 20px; font-weight: 700;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--muted);
    margin: 0;
    display: inline-block;  /* shrink the box to the text: a full-width block box
                               false-collides with top-right elements in the lint */
  }}
  .footer {{
    position: absolute;
    left: {LEFT}px; right: {RIGHT}px; bottom: {FOOT - 40}px;
    display: flex; justify-content: space-between; align-items: baseline;
    font-family: {SANS}; font-size: 20px;
  }}
  .footer .who {{ color: var(--muted); }}
  .footer .swipe {{ color: var(--accent); font-weight: 700; }}
  /* one accent underline element reused by several archetypes */
  .rule {{ height: 8px; background: var(--accent); border: none; border-radius: 2px; }}
  /* the slot the element layer fills later — empty + hidden for now */
  .element-slot {{ position: absolute; display: none; }}
  /* headline scale */
  .headline {{ font-family: {DISPLAY}; font-weight: 800; letter-spacing: -0.01em; line-height: 1.02; margin: 0; }}
</style>
{body}
<div class="footer">
  <span class="who">{_esc(AUTHOR)}</span>
  <span class="swipe">{cta}</span>
</div>
</div>"""


def _eyebrow(text):
    return f'<p class="eyebrow" data-lint="text">{_esc(text)}</p>' if text else ""


# --- archetypes -------------------------------------------------------------------

def number_hero(palette, story):
    """One giant accent numeral dominates; short bold caption below. Slot: upper-right."""
    num = _esc(story["number"])
    cap = _esc(story["caption"])
    body = f"""<div class="stage">
  {_eyebrow(story.get('eyebrow'))}
  <div class="element-slot" style="top:0; right:0; width:300px; height:300px;"></div>
  <div style="position:absolute; top:26%; left:0; right:0;">
    <div data-lint="text" style="font-family:{DISPLAY}; font-weight:800; font-size:340px;
         line-height:0.82; letter-spacing:-0.04em; color:var(--accent);">{num}</div>
    <p class="headline" data-lint="text" style="margin-top:44px; font-size:44px;
       max-width:78%; color:var(--ink);">{cap}</p>
  </div>
</div>"""
    return _shell(palette, body)


def statement(palette, story):
    """A flat, bold declarative headline with one accent underline. Slot: upper-right."""
    hl = _esc(story["headline"])
    body = f"""<div class="stage">
  {_eyebrow(story.get('eyebrow'))}
  <div class="element-slot" style="top:0; right:0; width:280px; height:280px;"></div>
  <div style="position:absolute; top:38%; left:0; right:0; transform:translateY(-50%);">
    <h1 class="headline" data-lint="text" style="font-family:{DISPLAY}; font-size:104px;
        max-width:96%; color:var(--ink);">{hl}</h1>
    <hr class="rule" style="width:180px; margin-top:52px;">
  </div>
</div>"""
    return _shell(palette, body)


def contrast(palette, story):
    """before -> after: muted 'before', accent 'after' (bigger), arrow between, caption.
    Slot: upper-right."""
    before = _esc(story["before"])
    after = _esc(story["after"])
    cap = _esc(story["caption"])
    body = f"""<div class="stage">
  {_eyebrow(story.get('eyebrow'))}
  <div class="element-slot" style="top:0; right:0; width:240px; height:240px;"></div>
  <div style="position:absolute; top:30%; left:0; right:0;">
    <div style="display:flex; align-items:baseline; gap:36px; flex-wrap:wrap;">
      <span data-lint="text" style="font-family:{DISPLAY}; font-weight:800; font-size:150px;
            color:var(--muted); line-height:0.9;">{before}</span>
      <span style="font-family:{SERIF}; font-size:88px; color:var(--ink);
            line-height:0.9;">&rarr;</span>
      <span data-lint="text" style="font-family:{DISPLAY}; font-weight:800; font-size:210px;
            color:var(--accent); line-height:0.9;">{after}</span>
    </div>
    <p class="headline" data-lint="text" style="margin-top:56px; font-size:42px;
       max-width:80%; color:var(--ink);">{cap}</p>
  </div>
</div>"""
    return _shell(palette, body, cta=story.get("cta", "swipe &raquo;"))


def index(palette, story):
    """A numbered teaser list: bold serif-ish headline, accent numerals down the left.
    Slot: upper-right."""
    hl = _esc(story["headline"])
    items = story["items"]
    rows = "\n".join(
        f'''<div style="display:flex; gap:28px; align-items:baseline; margin-bottom:30px;">
  <span data-lint="text" style="font-family:{SANS}; font-weight:800; font-size:40px;
        color:var(--accent); min-width:40px;">{i}</span>
  <span data-lint="text" style="font-size:36px; color:var(--ink);">{_esc(it)}</span>
</div>''' for i, it in enumerate(items, 1))
    body = f"""<div class="stage">
  {_eyebrow(story.get('eyebrow'))}
  <div class="element-slot" style="top:0; right:0; width:220px; height:220px;"></div>
  <h1 class="headline" data-lint="text" style="font-family:{DISPLAY}; font-size:64px;
      margin-top:70px; max-width:88%; color:var(--ink);">{hl}</h1>
  <div style="margin-top:64px;">{rows}</div>
</div>"""
    return _shell(palette, body)


def stat_grid(palette, story):
    """Four stats in a 2x2 grid; the first pops via SIZE + accent. Slot: upper-right."""
    stats = story["stats"]
    cells = []
    for i, (num, lab) in enumerate(stats):
        hot = i == 0
        size = 132 if hot else 96
        color = "var(--accent)" if hot else "var(--ink)"
        cells.append(f'''<div>
  <div data-lint="text" style="font-family:{DISPLAY}; font-weight:800; font-size:{size}px;
       line-height:0.9; color:{color};">{_esc(num)}</div>
  <div data-lint="text" style="margin-top:14px; font-size:30px; color:var(--muted);">{_esc(lab)}</div>
</div>''')
    grid = f'''<div style="display:grid; grid-template-columns:1fr 1fr; gap:70px 60px;
      align-items:end;">{''.join(cells)}</div>'''
    body = f"""<div class="stage">
  {_eyebrow(story.get('eyebrow'))}
  <div class="element-slot" style="top:0; right:0; width:200px; height:200px;"></div>
  <div style="position:absolute; top:34%; left:0; right:0;">{grid}</div>
</div>"""
    return _shell(palette, body)


def question(palette, story):
    """A big italic serif question with a huge translucent accent '?' behind it.
    The one archetype that leans on the DISPLAY SERIF (Georgia). Slot: below headline."""
    hl = _esc(story["headline"])
    body = f"""<div class="stage">
  <div data-lint="text" style="position:absolute; top:2%; right:-2%; font-family:{SERIF};
       font-weight:700; font-size:520px; line-height:0.8; color:var(--accent); opacity:0.9;">?</div>
  {_eyebrow(story.get('eyebrow'))}
  <h1 data-lint="text" style="position:absolute; top:44%; left:0; max-width:70%;
      font-family:{SERIF}; font-style:italic; font-weight:400; font-size:76px;
      line-height:1.1; color:var(--ink); margin:0;">{hl}</h1>
  <div class="element-slot" style="bottom:8%; left:0; width:200px; height:120px;"></div>
</div>"""
    return _shell(palette, body, serif_body=True)


def versus(palette, story):
    """Two stacked words with an accent 'vs' between; muted sub-line. Slot: upper-right."""
    left = _esc(story["left"])
    right = _esc(story["right"])
    sub = _esc(story["sub"])
    body = f"""<div class="stage">
  {_eyebrow(story.get('eyebrow'))}
  <div class="element-slot" style="top:0; right:0; width:240px; height:240px;"></div>
  <div style="position:absolute; top:34%; left:0; right:0;">
    <div data-lint="text" style="font-family:{DISPLAY}; font-weight:800; font-size:120px;
         line-height:1.0; color:var(--muted);">{left}</div>
    <div data-lint="text" style="font-family:{SERIF}; font-style:italic; font-size:56px;
         color:var(--accent); margin:8px 0 8px 4px;">vs</div>
    <div data-lint="text" style="font-family:{DISPLAY}; font-weight:800; font-size:120px;
         line-height:1.0; color:var(--ink);">{right}</div>
    <p data-lint="text" style="margin-top:44px; font-size:34px; color:var(--muted);">{sub}</p>
  </div>
</div>"""
    return _shell(palette, body)


def definition(palette, story):
    """A dictionary entry: big bold term, italic pronunciation, hairline, numbered defs.
    Slot: upper-right."""
    term = _esc(story["term"])
    pron = _esc(story["pron"])
    defs = story["defs"]
    rows = "\n".join(
        f'''<div style="display:flex; gap:24px; align-items:baseline; margin-bottom:26px;">
  <span data-lint="text" style="font-family:{SANS}; font-weight:800; font-size:34px;
        color:var(--accent);">{i}</span>
  <span data-lint="text" style="font-size:34px; line-height:1.25; color:var(--ink);
        max-width:640px;">{_esc(d)}</span>
</div>''' for i, d in enumerate(defs, 1))
    body = f"""<div class="stage">
  {_eyebrow(story.get('eyebrow'))}
  <div class="element-slot" style="top:0; right:0; width:200px; height:200px;"></div>
  <h1 data-lint="text" style="font-family:{DISPLAY}; font-weight:800; font-size:104px;
      margin:60px 0 0 0; letter-spacing:-0.01em; color:var(--ink);">{term}</h1>
  <p data-lint="text" style="font-family:{SERIF}; font-style:italic; font-size:30px;
     color:var(--muted); margin:18px 0 0 0;">{pron}</p>
  <hr style="border:none; border-top:1px solid var(--muted); opacity:0.4; margin:40px 0 44px 0;">
  <div>{rows}</div>
</div>"""
    return _shell(palette, body, serif_body=False)


# name -> function, for the demo mapper
TEMPLATES = {
    "number_hero": number_hero,
    "statement": statement,
    "contrast": contrast,
    "index": index,
    "stat_grid": stat_grid,
    "question": question,
    "versus": versus,
    "definition": definition,
}


# --- media toolkit (creative engine, chunk 1) ---------------------------------------
# Embeds real imagery into slides: data-URI images, treatment classes that force
# any photo into the slide's palette, chrome frames, and the license credit line.
# All deterministic - no model touches any of this.

MEDIA_CSS = """
  .duo-wrap { background: var(--accent); overflow: hidden; }
  .duo-wrap img { filter: grayscale(1) contrast(1.06); mix-blend-mode: multiply;
                  display: block; width: 100%; }
  /* dark grounds: multiply crushes to black, so SCREEN-blend instead - shadows
     melt into the ground, highlights wear the accent hue (sepia base is ~38deg,
     --duo-rot rotates it onto the palette accent; set by image_slot) */
  .duo-wrap.duo-dark { background: var(--ground); }
  .duo-wrap.duo-dark img { filter: grayscale(1) sepia(.85) hue-rotate(var(--duo-rot,0deg))
                           saturate(1.5) contrast(1.05); mix-blend-mode: screen; }
  .ht-wrap { position: relative; overflow: hidden; }
  .ht-wrap::after { content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image: radial-gradient(circle, rgba(0,0,0,.25) 1.5px, transparent 1.6px);
    background-size: 9px 9px; }
  .frame { border-radius: 14px; overflow: hidden; background: #fff;
           box-shadow: 0 24px 60px rgba(0,0,0,.16); }
  .frame-bar { height: 44px; display: flex; align-items: center; padding: 0 18px;
               gap: 8px; font-size: 15px; }
  .frame-dot { width: 13px; height: 13px; border-radius: 50%; display: inline-block; }
  .credit { font-size: 17px; color: var(--muted); }
"""


def img_data_uri(path):
    """Inline an image file as a data URI - the page stays self-contained."""
    import mimetypes
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def _hue_deg(hexcolor):
    """Hue of a #rrggbb colour in degrees (0-360)."""
    import colorsys
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360


def focal_y(path):
    """Vertical centre of visual interest as a percent (15-85): the centroid of
    edge energy (luminance gradients). A crop anchored here keeps the subject -
    a face, a chart body - instead of blindly keeping the top of the image."""
    from PIL import Image
    import numpy as np
    g = np.asarray(Image.open(path).convert("L").resize((96, 96)), dtype=float)
    energy = (np.abs(np.diff(g, axis=0))[:, :-1]
              + np.abs(np.diff(g, axis=1))[:-1, :]).sum(axis=1)
    if energy.sum() == 0:
        return 50
    c = (energy * np.arange(len(energy))).sum() / energy.sum() / 96 * 100
    return int(min(85, max(15, round(c))))


def image_slot(path, treatment="none", style="", dark=False, accent=None, focal=None):
    """An embedded image with an optional palette-forcing treatment.
    treatment: none | duotone (remapped into the accent) | halftone (dot overlay).
    dark+accent: duotone flips to the screen-blend dark variant tinted to accent.
    focal (0-100): cover-crop anchored at that vertical centre - the wrapper's
    style must give the slot its height, the image fills and crops around focal."""
    cls = {"duotone": "duo-wrap", "halftone": "ht-wrap"}.get(treatment, "")
    if treatment == "duotone" and dark:
        cls += " duo-dark"
        style += f" --duo-rot:{(_hue_deg(accent) - 38) % 360:.0f}deg;" if accent else ""
    img_css = "display:block;width:100%;"
    if focal is not None:
        img_css = (f"display:block;width:100%;height:100%;object-fit:cover;"
                   f"object-position:center {int(focal)}%;")
    return (f'<div class="{cls}" style="{style}">'
            f'<img src="{img_data_uri(path)}" style="{img_css}"></div>')


def browser_frame(inner, url_label=""):
    """Wrap content in macOS-browser chrome (for real screenshots / reconstructions)."""
    return f"""<div class="frame">
  <div class="frame-bar" style="background:#e8e4df;color:#666;">
    <span class="frame-dot" style="background:#ff5f57;"></span>
    <span class="frame-dot" style="background:#febc2e;"></span>
    <span class="frame-dot" style="background:#28c840;"></span>
    <span style="margin-left:14px;">{_esc(url_label)}</span>
  </div>{inner}</div>"""


def terminal_frame(inner, title="terminal"):
    """Wrap monospace content in dark terminal chrome (for real command output)."""
    return f"""<div class="frame" style="background:#1a1b21;">
  <div class="frame-bar" style="background:#2a2c35;color:#9aa0b0;">
    <span class="frame-dot" style="background:#ff5f57;"></span>
    <span class="frame-dot" style="background:#febc2e;"></span>
    <span class="frame-dot" style="background:#28c840;"></span>
    <span style="margin-left:14px;">{_esc(title)}</span>
  </div>
  <pre style="margin:0;padding:26px 30px;font-family:'SF Mono',Menlo,monospace;
    font-size:22px;line-height:1.55;color:#d6dae3;white-space:pre-wrap;">{inner}</pre>
</div>"""


def credit_line(text):
    """The visible attribution line the license gate requires for CC-BY assets."""
    return f'<div class="credit" data-credit="1">{_esc(text)}</div>'


def _demo():
    """Render one PNG per sampled archetype with a sample palette.
    Runnable check: asserts each renders and passes the browser layout lint."""
    from pathlib import Path
    import palette_gen
    from render_html import render

    pal = palette_gen.make_palette(210, False, False)  # blue-on-light: always valid
    samples = {
        "number_hero": {"eyebrow": "AI reliability", "number": "70%",
                        "caption": "of AI agent runs miss a multi-step task on the first try"},
        "statement": {"eyebrow": "the take", "headline": "Bigger models are not the fix"},
        "contrast": {"eyebrow": "before / after", "before": "9 s", "after": "0.6 s",
                     "caption": "one index change cut our p95 latency"},
        "index": {"eyebrow": "in production", "headline": "5 prompts that break silently",
                  "items": ["the empty retrieval", "the 8k token overflow",
                            "the silent truncation", "the locale mismatch", "the stale cache"]},
        "stat_grid": {"eyebrow": "one AI feature, fully loaded",
                      "stats": [["$0.03", "per call"], ["4", "model hops"],
                                ["900ms", "p95 latency"], ["12%", "cache hits"]]},
        "question": {"eyebrow": "gut check", "headline": "Is your RAG actually retrieving?"},
    }
    out_dir = Path(__file__).parent / "drafts"
    for name, story in samples.items():
        html_str = TEMPLATES[name](pal, story)
        out = out_dir / f"_tmpl_{name}.png"
        render(html_str, out, check=True)  # raises if it clips/overlaps
        print("ok", out)


if __name__ == "__main__":
    _demo()
