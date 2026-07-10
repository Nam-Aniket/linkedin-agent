# linkedin-agent

A deterministic LinkedIn content pipeline built to be driven by a coding agent
(Claude Code, Cursor, Codex, anything that can read a repo and run Python).

It takes a topic from "maybe interesting" to a published post - with mechanical
quality gates at every step - while **you** stay the editor-in-chief: nothing is
ever published without your explicit OK.

```
scout -> rank -> research gate -> design (covers/carousels) -> copy gate -> YOUR approval -> publish -> track
```

## The interesting part: it has no taste until you give it yours

All the machinery is here - palette generation with WCAG contrast gates, cover
archetypes, a composition grammar with novelty gates, carousel assembly,
AI-slop copy linting, design scoring, an engagement tracker that learns which
of your designs work. But every aesthetic and editorial decision (your niche,
your voice, your colors, your fonts, your eval thresholds) lives in one file:
`profile.json` - and that file does not exist until your agent interviews you.

**So: clone it, open it with your coding agent, and say "set me up."**
The agent's first move (per [AGENTS.md](AGENTS.md)) is to run the interview in
[ONBOARDING.md](ONBOARDING.md) - one question at a time - and paint the blank
slate with *your* answers. Two people who clone this repo end up with two
pipelines that post visibly different things.

## What's inside

| stage | files | what it does |
|---|---|---|
| scout | `scout.py`, `gh_metrics.py` | HN / HuggingFace / GitHub velocity + your own repos as story mines |
| rank | `topic_engine.py`, `daily.py` | value-density ranking of your backlog (`ideas.md`), morning shortlist |
| research gate | `research_check.py` | briefs must carry verified claims, dates, primary sources |
| design | `palette_gen.py`, `html_templates.py`, `element.py`, `compose.py`, `render_covers.py`, `render_html.py`, `assets.py` | generated palettes, 8 cover archetypes, per-topic marks, composition grammar with design-novelty gates, licensed-asset resolver |
| carousel | `html_deck.py` | tagged story -> gated multi-slide PDF |
| copy gate | `check.py` | banned phrases, AI-rhythm tells, plain-language lint, hook preview |
| design eval | `design_score.py`, `design_lint.py` | pixel-level composition scoring + browser layout lint |
| publish | `post.py`, `auth.py` | LinkedIn API (text / image / document posts), preview-first, `--confirm` required |
| learn | `tracker.py` | logs every post's design attributes + your picks; engagement data turns taste into thresholds |

Design work is deterministic and eval-gated - the LLM's job is judgment and
copy, never pixels. Same story in, same covers out, on any machine.

## Setup (your agent does this for you in onboarding)

```bash
# main environment (python 3.10+)
pip install -r requirements.txt

# renderer venv (headless Chromium lives here, isolated on purpose)
python3 -m venv .venv-render
.venv-render/bin/pip install playwright
.venv-render/bin/playwright install chromium

# smoke test
.venv-render/bin/python render_html.py     # renders drafts/_render_smoke.png
python3 html_deck.py                       # renders the full demo deck PDF

# LinkedIn credentials (your own app - see ONBOARDING.md step 6)
cp .env.example .env                       # fill in your client id/secret
python3 auth.py                            # one-time OAuth -> token.json
```

Every module has an offline `--selftest`; run them all with:

```bash
for m in config check element palette_gen compose tracker topic_engine daily \
         scout assets research_check gh_metrics design_lint design_score html_deck; do
  python3 $m.py --selftest || break; done
```

## Hard rules baked in

- **Nothing publishes without `--confirm`**, and your agent must show you the
  final image + full copy and get your explicit OK first.
- Every factual claim in a post needs a source fetched *now* (the research gate
  blocks unverified briefs).
- Only properly licensed imagery (CC0 / public domain / CC BY with visible
  credit) - the license gate blocks the rest. No AI-generated imagery.
- Engagement bait is linted out. Links go in the first comment, not the body.

## License

MIT. Vendored SVGs: Tabler Icons (MIT) and Simple Icons (CC0) - see
`elements/NOTICE`. Brand logos remain trademarks of their owners.
