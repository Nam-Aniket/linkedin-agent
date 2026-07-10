# Onboarding interview - paint the blank slate

You (the coding agent) run this ONCE, when `profile.json` does not exist. The
goal: by the end, the pipeline carries the USER's niche, voice, and design
taste - not the defaults, and not the taste of whoever you saw in training data.

Method: ask ONE question at a time in chat. Each question builds on the last
answer. Offer concrete options where taste is hard to verbalize (people pick
better than they describe). Write `profile.json` incrementally (schema with all
keys: the `config.py` docstring). Confirm the final file with the user.

## Step 0 - environment

Before the interview, quietly make sure the machinery runs:

```bash
pip install -r requirements.txt
python3 -m venv .venv-render
.venv-render/bin/pip install playwright
.venv-render/bin/playwright install chromium
.venv-render/bin/python render_html.py   # smoke: drafts/_render_smoke.png
```

If anything fails, fix it with the user before interviewing.

## Step 1 - identity

Ask for: the name that should sign every slide (footer), and a contact email
(only used in a polite API User-Agent - never published).
-> `author`, `contact`

## Step 2 - niche and audience

Ask, one at a time:
1. What do you want to be known for? (their subject area, in their words)
2. Who should stop scrolling? (role/audience - shapes voice and jargon rules)
3. What are 3-6 search phrases where your audience's PAIN shows up in public?
   (these become HN pain-thread queries)
4. How often do you want to post? (sets the backlog floor: ~7 for daily,
   ~3 for twice a week)

Derive and confirm: `niche.hn_query` (an OR-query of their core terms),
`niche.gh_scout_query`, `niche.pain_queries`, `niche.backlog_floor`.

## Step 3 - own work (the best content mine)

Posts about things the user actually built usually beat commentary. Ask:
- Which folders on this machine hold your project repos? (-> `own_work.repo_roots`,
  scanned 1 level deep for git activity; empty list = feature off)
- Any repo folder names that differ from the project's public name?
  (-> `own_work.repo_alias`)
- Do you keep any kind of work log / failure log / TIL notes as markdown with
  `### YYYY-MM-DD - title` headings? (-> `failure_log`, `learning_log`)

## Step 4 - voice and design taste

Voice: ask for words/phrases that make them cringe (-> `voice.banned_extra`)
and field jargon their AUDIENCE speaks natively (so it should NOT be linted;
anything else stays plain-language gated; extra swaps -> `voice.jargon_extra`).

Design - do this with PICTURES, not adjectives:

1. **Moods.** Ask: "when your posts land, what should they feel like?" Build a
   vocabulary of 4-6 mood words WITH the user (e.g. urgent, calm, playful,
   authoritative). For each, pick a base hue (0-360) and light or dark ground
   with them - render 2-3 candidate palettes per mood via
   `python3 palette_gen.py` sheets or small test covers and let them point.
   -> `design.moods` as `{"mood": [hue, dark?]}`
2. **Saturation.** Muted-and-premium vs loud-and-bold? Render the same cover at
   `accent_saturation` 0.45 / 0.60 / 0.80 and let them pick.
   -> `design.accent_saturation`, `design.ground_saturation` (0.05-0.20)
3. **Display font.** Offer 4-6 open-license display faces with different
   personalities (browse fonts.google.com - all OFL; e.g. a geometric black, a
   slab, a grotesque, a rounded, a serif display). Download the winner's TTF
   into `elements/fonts/`, set `design.fonts.display_name` + `display_file`,
   re-render a cover so they see it live. (No pick is fine too - system sans.)

## Step 5 - calibrate the design evals to THEIR taste

The shipped `design_score.py` bands are permissive on purpose - they know
nothing about the user yet. Calibrate:

1. Render the showcase with their profile: `python3 render_covers.py` and
   `python3 html_deck.py` - show the contact sheet.
2. Iterate moods/saturation/font until they'd happily post ~8 of 10 covers.
3. Measure their approved set: `python3 design_score.py --measure drafts/cover_*.png`
4. Set each band just OUTSIDE the measured envelope in `profile.json` under
   `thresholds.cover` (and later `thresholds.media` once they've rendered
   media covers). The gate should catch regressions from THEIR normal - it is
   a taste fence, so it must be built from their measurements, nobody else's.

## Step 6 - LinkedIn credentials (theirs, never shared)

Walk the user through, don't do it for them where it needs a browser:

1. https://www.linkedin.com/developers/ -> create an app (needs a LinkedIn page
   to associate; a bare personal page works).
2. Add the "Share on LinkedIn" and "Sign In with LinkedIn using OpenID Connect"
   products; add `http://localhost:3000/callback` as an authorized redirect URL.
3. `cp .env.example .env`, fill LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET.
4. `python3 auth.py` - browser OAuth, writes `token.json` (60-day token;
   re-run when it expires). `.env` and `token.json` are gitignored - keep them so.
5. Verify with a dry run: `python3 post.py --text "test" ` (no --confirm =
   preview only, nothing publishes).

## Step 7 - seal it

1. Show the user the final `profile.json` and confirm it reads back correctly.
2. Create `ideas.md` with 2-3 starter ideas from a live scout run
   (`python3 scout.py floor`) that THEY pick.
3. Restate the two operating promises: nothing publishes without their explicit
   OK, and every claim gets verified at write time.
4. Hand back: "you're onboarded - say 'post about X' or just 'what should I
   post today?'" From now on AGENTS.md's operating loop applies.
