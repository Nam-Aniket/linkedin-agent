#!/usr/bin/env python3
"""One-time LinkedIn OAuth. Opens browser, catches the callback on localhost:3000,
exchanges the code for a 60-day access token, fetches the person URN, saves token.json."""
import http.server, socketserver, urllib.parse, urllib.request, urllib.error
import json, webbrowser, sys, time
from pathlib import Path

HERE = Path(__file__).parent
ENV = {}
for line in (HERE / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        ENV[k.strip()] = v.strip()

CLIENT_ID = ENV["LINKEDIN_CLIENT_ID"]
CLIENT_SECRET = ENV["LINKEDIN_CLIENT_SECRET"]
REDIRECT_URI = ENV.get("LINKEDIN_REDIRECT_URI", "http://localhost:3000/callback")
SCOPE = "openid profile w_member_social"
STATE = "linkedin-pipeline-oauth"

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "state": STATE,
    "scope": SCOPE,
})

result = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if "code" in params:
            result["code"] = params["code"][0]
            self.wfile.write(b"<h1>Authorized.</h1><p>Close this tab and return to Claude.</p>")
        elif "error" in params:
            result["error"] = params.get("error_description", params["error"])[0]
            self.wfile.write(b"<h1>Error</h1><p>" + result["error"].encode() + b"</p>")

    def log_message(self, *a):
        pass


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def get_json(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main():
    print("Open this URL if the browser did not open automatically:\n" + AUTH_URL + "\n", flush=True)
    webbrowser.open(AUTH_URL)
    with socketserver.TCPServer(("localhost", 3000), Handler) as httpd:
        httpd.timeout = 1
        start = time.time()
        while not result and time.time() - start < 300:
            httpd.handle_request()
    if "error" in result:
        sys.exit("OAuth error: " + result["error"])
    if "code" not in result:
        sys.exit("Timed out after 5 min waiting for authorization.")

    print("Exchanging code for access token...", flush=True)
    try:
        tok = post_form("https://www.linkedin.com/oauth/v2/accessToken", {
            "grant_type": "authorization_code",
            "code": result["code"],
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        })
    except urllib.error.HTTPError as e:
        sys.exit("Token exchange failed: " + e.read().decode())

    access_token = tok["access_token"]
    info = get_json("https://api.linkedin.com/v2/userinfo", access_token)
    out = {
        "access_token": access_token,
        "expires_in": tok.get("expires_in"),
        "obtained_at": int(time.time()),
        "person_urn": f"urn:li:person:{info['sub']}",
        "name": info.get("name"),
    }
    (HERE / "token.json").write_text(json.dumps(out, indent=2))
    days = round(tok.get("expires_in", 0) / 86400, 1)
    print(f"\nSUCCESS. Token saved for {info.get('name')} ({out['person_urn']}). "
          f"Valid ~{days} days.", flush=True)


if __name__ == "__main__":
    main()
