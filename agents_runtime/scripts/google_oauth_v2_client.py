"""Google OAuth com client do token existente (projeto 180096224219)."""
import json
import os
import tempfile
import http.server
import urllib.parse
import requests
import time

# Usando client do token_drive.json (que ja funcionou antes)
CLIENT_ID = "180096224219-nn15kc103k1hni9u868i8d3qo1ihim32.apps.googleusercontent.com"
CLIENT_SECRET = "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"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
REDIRECT_PORT = 8088

auth_code = None

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        qs = urllib.parse.urlparse(self.path).query
        auth_code = urllib.parse.parse_qs(qs).get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK" if auth_code else b"ERR")
    def log_message(self, *a): pass

REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode({
    "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
    "scope": " ".join(SCOPES), "response_type": "code",
    "access_type": "offline", "prompt": "consent",
})

print(auth_url)
print(f"\nServidor em http://localhost:{REDIRECT_PORT} - 120s\n")

server = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
start = time.time()
while not auth_code and time.time() - start < 120:
    server.handle_request()

if not auth_code:
    print("Timeout.")
    exit(1)

r = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
    "code": auth_code, "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
})
if r.status_code != 200:
    print(f"ERRO: {r.text}")
    exit(1)

tok = r.json()
td = {
    "token": tok["access_token"], "refresh_token": tok.get("refresh_token", ""),
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
    "scopes": SCOPES,
    "expiry": (__import__("datetime").datetime.now(__import__("datetime").UTC) +
               __import__("datetime").timedelta(seconds=tok.get("expires_in", 3600))).isoformat() + "Z",
}
print(f"Access: {tok['access_token'][:20]}... Ref: {tok.get('refresh_token','')[:10]}...")

tmp = os.path.join(tempfile.gettempdir(), "google_oauth_calendar.json")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(td, f, ensure_ascii=False)
print(os.popen(f'gcloud secrets versions add google-oauth-token --data-file="{tmp}" --project=coherence-ominichannel-fs').read())
os.unlink(tmp)
print("DONE!")
