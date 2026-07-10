# Instructions for coding agents (Claude Code, Cursor, Codex, ...)

## FIRST-RUN GATE - read this before anything else

If `profile.json` does NOT exist in the repo root, this pipeline has no owner
yet: no niche, no voice, no design taste, no eval thresholds. **Do not scout,
design, draft, or publish anything.** Your first and only job is to run the
onboarding interview in [ONBOARDING.md](ONBOARDING.md):

- Ask ONE question at a time, in the user's chat, and build on their answers.
- Write their answers into `profile.json` as you go (schema: `config.py` docstring).
- Finish with the calibration step (render samples, tune until they like what
  they see, then set the design_score thresholds from measurements).

Only after `profile.json` exists do the operating instructions below apply.

## The operating loop (idea -> published post)

Work in the repo root. Every gate below is mandatory; order matters.

0. **Format gate.** The user's words pick the format, and it never changes
   mid-flow without asking them: "image post" = ONE cover via
   `compose.pick_flow` published with `post.py --image`; "carousel"/"deck" =
   `html_deck.render_deck` published with `post.py --carousel <pdf>`. Never
   publish a deck page (deck_N.png) as an image - post.py hard-blocks it.
   Restate the format in the approval preview. Grounds rotate automatically
   (no two dark grounds in a row); if the user explicitly wants dark, set
   `story["ground"] = "dark"`.

1. **Stock the backlog.** `python3 scout.py floor` - if below the floor, show
   the user the candidates, let them pick keepers, paste keepers into
   `ideas.md` and set utility/surprise/capability (0-3) with them.
2. **Pick the topic.** `python3 topic_engine.py --brief` ranks the backlog and
   writes `drafts/brief_<slug>.json` for the winner (or the user brings their
   own topic/image - then write the brief yourself).
3. **Research gate.** Fill the brief's claim/metric/recency/primary_source/
   verified fields from sources you fetch NOW - never from memory, never from
   the idea text as pasted (viral copy fossilizes stale claims). For GitHub
   topics run `python3 gh_metrics.py <url>` and prefer RISING/EXPLODING.
   Then `python3 research_check.py --brief drafts/brief_<slug>.json` must PASS.
4. **Design.** Build the deck dict (see `html_deck.py` DEMO for the shape) and
   call `html_deck.render_deck`. Media covers (an `asset` on the cover slide)
   trigger the 3-variant pick flow: show the user the contact strip, they pick,
   the pick is logged (that is how the sampler learns their taste). Assets only
   via `assets.py` (licensed) or files the user supplies.
5. **Copy gate.** Draft the post text in the user's voice (see profile.json
   voice notes). `python3 check.py --text-file <draft>` must PASS - fix what it
   flags, don't argue with the gate. Links go in the FIRST COMMENT, never the body.
6. **APPROVAL GATE - absolute.** Show the user the final visual(s) and the full
   copy in chat. Publish ONLY after their explicit OK, via:
   `python3 post.py --carousel <pdf>|--image <png> --text-file <txt> --confirm`
   then the first comment: `post.py --comment-on <urn> --comment "..." --confirm`.
   Without `--confirm` everything is preview-only - that is by design.
7. **Close the loop.** Verify the post landed in `tracking.csv`. Next day, ask
   for the 24h numbers (`python3 tracker.py due` lists what's owed) - the
   LinkedIn API can post but cannot read engagement, so the user types them.

## Standing rules

- NEVER publish, comment, or re-post without the user's explicit OK in chat.
- Every specific (number, version, star count, price, date) traces to a source
  fetched this session, or it does not ship.
- No AI-generated imagery. Only licensed assets with visible credit when the
  license requires it (the deck lint enforces this - do not bypass it).
- Rejections are data: when the user rejects a design or copy, ask what's off,
  then re-render - never re-offer a rejected variant.
- If a gate blocks (novelty, design score, layout lint), read its printed
  reason and fix the CONTENT; lowering a gate's bar is the user's call, not yours.
- The eval thresholds in profile.json belong to the user's taste. Recalibrate
  (ONBOARDING.md step 5) only when they say the gate is fighting them.
