import json, os, tempfile, http.server, urllib.parse, requests, time, sys

CLIENT_ID = "894828119087-goo6lcl6vgm5bdq5qgafscb8qbr4ueet.apps.googleusercontent.com"
CLIENT_SECRET = "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"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
PORT = 8080

auth_code = [None]

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        auth_code[0] = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK" if auth_code[0] else b"ERR")
    def log_message(self, *a): pass

auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode({
    "client_id": CLIENT_ID,
    "redirect_uri": f"http://localhost:{PORT}",
    "scope": " ".join(SCOPES),
    "response_type": "code",
    "access_type": "offline",
    "prompt": "consent",
})

print("=== ABRA ESTE LINK NO NAVEGADOR ===")
print(auth_url)
print("====================================")
print(f"\nServidor aguardando em http://localhost:{PORT} por 120s...\n", flush=True)

server = http.server.HTTPServer(("localhost", PORT), H)
start = time.time()
while not auth_code[0] and time.time() - start < 120:
    server.handle_request()

if not auth_code[0]:
    print("TIMEOUT: Nenhum code recebido.")
    sys.exit(1)

print(f"\nCode recebido. Trocando por token...", flush=True)
r = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": auth_code[0],
    "redirect_uri": f"http://localhost:{PORT}",
    "grant_type": "authorization_code",
})

if r.status_code != 200:
    print(f"ERRO: {r.status_code} {r.text}")
    sys.exit(1)

tok = r.json()
td = {
    "token": tok["access_token"],
    "refresh_token": tok.get("refresh_token", ""),
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scopes": SCOPES,
    "expiry": (__import__("datetime").datetime.now(__import__("datetime").UTC) +
               __import__("datetime").timedelta(seconds=tok.get("expires_in", 3600))).isoformat() + "Z",
}
print(f"Access: {tok['access_token'][:20]}...")
if tok.get("refresh_token"):
    print(f"Refresh: {tok['refresh_token'][:10]}...")

tmp = os.path.join(tempfile.gettempdir(), "goog_oauth_final.json")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(td, f, ensure_ascii=False)

print("\nUpload GCP...", flush=True)
result = os.popen(f'gcloud secrets versions add google-oauth-token --data-file="{tmp}" --project=coherence-ominichannel-fs').read()
print(result)
os.unlink(tmp)
print("DONE!")
