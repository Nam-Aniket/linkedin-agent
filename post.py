#!/usr/bin/env python3
"""Publish to LinkedIn personal profile via the ugcPosts API.
Optionally attach an image and add a first comment (e.g. the link we keep out of the body).

Usage:
  python3 post.py --text-file draft.txt [--image card.png] [--comment "note + https://link"]
  python3 post.py --text "inline" --dry-run     # prints what it would do, no network

Reads the access token + person URN from token.json (created by auth.py).
"""
import argparse, json, sys, time, mimetypes, urllib.request, urllib.error, urllib.parse
from pathlib import Path

HERE = Path(__file__).parent
API = "https://api.linkedin.com"


def _deck_manifest(pdf_path):
    """The design manifest html_deck writes next to the PDF (None if absent)."""
    p = Path(pdf_path).with_suffix(".json")
    return json.loads(p.read_text()) if p.exists() else None


def _quality_gates(text, manifest, confirm):
    """Pre-publish content gates: novelty (no self-repeats) + no demo data in a real post.
    Prints verdicts in preview; BLOCKS on --confirm. Returns list of blockers."""
    import tracker
    blockers = []
    probe = text + " " + " ".join((manifest or {}).get("headlines", []))
    sim, closest = tracker.novelty(probe)
    if sim > 0.5:
        blockers.append(f"novelty: {sim:.0%} trigram overlap with a published post ('{closest}...')")
    elif sim > 0.3:
        print(f"novelty WARN: {sim:.0%} overlap with '{closest}...' - is this a re-tread?")
    else:
        print(f"novelty ok ({sim:.0%} max overlap with history)")
    for src in (manifest or {}).get("sources", []):
        if "illustrative" in src.lower() or "demo" in src.lower():
            blockers.append(f"chart source is placeholder data: '{src}' - a real post needs real sourced numbers")
    if blockers and not confirm:
        for b in blockers:
            print("WOULD BLOCK at --confirm: " + b)
        return []
    return blockers


def load_token():
    t = json.loads((HERE / "token.json").read_text())
    remaining = t["expires_in"] - (time.time() - t["obtained_at"])
    if remaining <= 0:
        sys.exit("Token expired. Re-run: python3 auth.py")
    if remaining < 5 * 86400:
        print(f"WARNING: token expires in {round(remaining/86400, 1)} days — re-auth soon.",
              file=sys.stderr)
    return t


def api_post(path, token, body):
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "X-Restli-Protocol-Version": "2.0.0"})
    with urllib.request.urlopen(req) as r:
        return r.status, dict(r.headers), r.read().decode()


def upload_image(token, person_urn, image_path):
    """Register + upload a single image, return its asset URN."""
    body = {"registerUploadRequest": {
        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
        "owner": person_urn,
        "serviceRelationships": [
            {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}]}}
    _, _, resp = api_post("/v2/assets?action=registerUpload", token, body)
    v = json.loads(resp)["value"]
    upload_url = v["uploadMechanism"][
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    ctype = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
    req = urllib.request.Request(upload_url, data=Path(image_path).read_bytes(),
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": ctype}, method="POST")
    try:
        urllib.request.urlopen(req).read()
    except urllib.error.HTTPError as e:
        sys.exit(f"Image upload failed ({e.code}): {e.read().decode()[:200]}")
    return v["asset"]


def build_share(person_urn, text, asset=None):
    if asset:
        content = {"shareCommentary": {"text": text}, "shareMediaCategory": "IMAGE",
                   "media": [{"status": "READY", "media": asset}]}
    else:
        content = {"shareCommentary": {"text": text}, "shareMediaCategory": "NONE"}
    return {"author": person_urn, "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": content},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}}


def add_comment(token, person_urn, post_urn, text):
    enc = urllib.parse.quote(post_urn, safe="")
    return api_post(f"/v2/socialActions/{enc}/comments", token,
                    {"actor": person_urn, "message": {"text": text}})


API_VERSION = "202606"   # current LinkedIn versioned-API month (YYYYMM); doc default li-lms-2026-06


def _versioned_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "LinkedIn-Version": API_VERSION, "X-Restli-Protocol-Version": "2.0.0"}


def upload_document(token, person_urn, pdf_path):
    """Register + upload a PDF via the versioned Documents API; return the document URN.
    Publishes nothing on its own — the asset only appears once attached to a post."""
    size = Path(pdf_path).stat().st_size
    if size > 100 * 1024 * 1024:
        sys.exit(f"PDF is {size / 1e6:.0f}MB — LinkedIn caps documents at 100MB")
    req = urllib.request.Request(
        API + "/rest/documents?action=initializeUpload",
        data=json.dumps({"initializeUploadRequest": {"owner": person_urn}}).encode(),
        method="POST", headers=_versioned_headers(token))
    try:
        with urllib.request.urlopen(req) as r:
            v = json.loads(r.read().decode())["value"]
    except urllib.error.HTTPError as e:
        sys.exit(f"initializeUpload failed ({e.code}): {e.read().decode()[:300]}")
    # explicit Content-Type: without it urllib stamps x-www-form-urlencoded and the
    # upload host 400s (same latent bug the image path had, fixed 2026-07-06)
    put = urllib.request.Request(v["uploadUrl"], data=Path(pdf_path).read_bytes(),
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/pdf"}, method="PUT")
    try:
        urllib.request.urlopen(put).read()
    except urllib.error.HTTPError as e:
        sys.exit(f"PDF upload failed ({e.code}): {e.read().decode()[:200]}")
    return v["document"]


def build_document_post(person_urn, text, doc_urn, title):
    return {"author": person_urn, "commentary": text, "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                             "thirdPartyDistributionChannels": []},
            "content": {"media": {"title": title, "id": doc_urn}},
            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}


def post_document(token, person_urn, text, pdf_path, title):
    """Upload the PDF, then create the document post. Returns (status, post_urn)."""
    doc_urn = upload_document(token, person_urn, pdf_path)
    print(f"Document uploaded: {doc_urn}")
    req = urllib.request.Request(
        API + "/rest/posts",
        data=json.dumps(build_document_post(person_urn, text, doc_urn, title)).encode(),
        method="POST", headers=_versioned_headers(token))
    try:
        with urllib.request.urlopen(req) as r:
            status, headers = r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        sys.exit(f"Post creation failed ({e.code}): {e.read().decode()[:300]}")
    return status, headers.get("x-restli-id") or headers.get("X-RestLi-Id")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--image")
    ap.add_argument("--carousel", help="path to a carousel PDF — post it as a LinkedIn document")
    ap.add_argument("--title", help="document title shown in the feed chip (default: deck "
                                    "manifest subject, else the PDF filename)")
    ap.add_argument("--comment")
    ap.add_argument("--comment-on", help="URN of an existing post to comment on, then exit")
    ap.add_argument("--dry-run", action="store_true", help="preview only (same as omitting --confirm)")
    ap.add_argument("--confirm", action="store_true",
                    help="REQUIRED to actually publish. Without it, everything is preview-only.")
    a = ap.parse_args()

    # the learning loop's nudge: whenever you touch the publisher, surface any
    # posts whose 24h/7d numbers are due (recording is manual - API can't read counts)
    try:
        import tracker
        for r, w in tracker.due():
            print(f"[loop] {w} numbers due: python3 tracker.py record --urn {r['post_urn']} "
                  f"--impressions-{w} N --reactions-{w} N --comments-{w} N")
    except Exception:
        pass

    if a.comment_on:
        if not a.comment:
            sys.exit("--comment-on needs --comment text")
        if not a.confirm:
            print("PREVIEW — would comment on " + a.comment_on + ":\n" + "-" * 56)
            print(a.comment)
            print("-" * 56 + "\nNothing posted. Re-run with --confirm to publish.")
            return
        t = load_token()
        cs, _, _ = add_comment(t["access_token"], t["person_urn"], a.comment_on, a.comment)
        print(f"Comment added ({cs}) to {a.comment_on}")
        return

    text = a.text or (Path(a.text_file).read_text().strip() if a.text_file else None)
    if not text:
        sys.exit("Provide --text or --text-file")

    manifest = _deck_manifest(a.carousel) if a.carousel else \
        _deck_manifest(a.image) if a.image else None

    if not a.confirm:
        print("PREVIEW — would post to your profile:\n" + "=" * 56)
        print(text)
        print("=" * 56)
        if a.image:
            print(f"[image attached: {a.image}]")
        if a.carousel:
            print(f"[carousel PDF attached: {a.carousel}]"
                  + (f" [deck: {manifest['slides']} slides, {manifest['archetype']} cover]"
                     if manifest else " [no deck manifest - tracker will not auto-log]"))
        if a.comment:
            print(f"[first comment: {a.comment}]")
        _quality_gates(text, manifest, confirm=False)
        print("\nNothing posted. Re-run with --confirm to publish.")
        return

    blockers = _quality_gates(text, manifest, confirm=True)
    if blockers:
        sys.exit("BLOCKED by content gates:\n  - " + "\n  - ".join(blockers)
                 + "\nFix the content (or the history log) and re-run.")

    t = load_token()
    token, person = t["access_token"], t["person_urn"]

    if a.carousel:
        # the title is PUBLIC feed chrome (the "name · N pages" chip over the cover) -
        # a filename stem like "openwiki_deck" reads mechanical, so prefer a human title
        title = a.title or (manifest or {}).get("subject") or Path(a.carousel).stem
        status, post_urn = post_document(token, person, text, a.carousel, title)
    else:
        asset = upload_image(token, person, a.image) if a.image else None
        if asset:
            print(f"Image uploaded: {asset}")
        status, headers, _ = api_post("/v2/ugcPosts", token, build_share(person, text, asset))
        post_urn = headers.get("X-RestLi-Id") or headers.get("x-restli-id")
    print(f"POSTED ({status}). URN: {post_urn}")

    if a.comment and post_urn:
        try:
            cs, _, _ = add_comment(token, person, post_urn, a.comment)
            print(f"First comment added ({cs}).")
        except urllib.error.HTTPError as e:
            print(f"Comment failed ({e.code}): {e.read().decode()[:200]}\n"
                  f"Post is live — add the comment manually.", file=sys.stderr)

    # auto-log into the design learning loop (tracking.csv); never blocks a live post
    try:
        import tracker
        m = manifest or {}
        sc = m.get("scores", {})
        tracker.log_post(
            date=time.strftime("%Y-%m-%d"), post_urn=post_urn or "",
            format="carousel" if a.carousel else ("image" if a.image else "text"),
            archetype=m.get("archetype", ""), palette_dark=m.get("palette_dark", ""),
            accent=m.get("accent", ""), element_kind=m.get("element_kind", ""),
            hook=m.get("hook", ""), mood=m.get("mood", ""),
            composition=m.get("composition", ""), asset_url=m.get("asset_url", ""),
            whitespace=sc.get("whitespace", ""), dominance=sc.get("dominance", ""),
            balance_y=sc.get("balance_y", ""), glance=sc.get("glance", ""),
            copy_hook=text[:90])
        print("Logged to tracking.csv - record 24h numbers with: "
              f"python3 tracker.py record --urn {post_urn} --impressions-24h N ...")
    except Exception as e:                      # logging must never kill a live publish
        print(f"tracker logging failed ({e}) - log manually", file=sys.stderr)

    print(f"View: https://www.linkedin.com/feed/update/{post_urn}")


if __name__ == "__main__":
    main()
