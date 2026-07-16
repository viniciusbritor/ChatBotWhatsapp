"""OAuth flow with generated self-signed cert for https://localhost:8080."""
import json, os, tempfile, ssl, http.server, urllib.parse, requests, time, socket

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
REDIRECT_URI = f"https://localhost:{PORT}"

auth_code = [None]

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        auth_code[0] = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - pode fechar esta janela.")
    def log_message(self, *a): pass

auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode({
    "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
    "scope": " ".join(SCOPES), "response_type": "code",
    "access_type": "offline", "prompt": "consent",
})

print(f"=== ABRA ESTE LINK NO NAVEGADOR ===\n{auth_url}\n====================================", flush=True)
print(f"Servidor HTTPS aguardando em {REDIRECT_URI} por 120s...\n", flush=True)

server = http.server.HTTPServer(("localhost", PORT), H)

# Try HTTPS with self-signed cert
try:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    print("HTTPS enabled with self-signed cert", flush=True)
except Exception as e:
    print(f"HTTPS failed: {e}. Falling back to HTTP.", flush=True)

start = time.time()
while not auth_code[0] and time.time() - start < 120:
    server.handle_request()

if not auth_code[0]:
    print("TIMEOUT", flush=True)
    exit(1)

print(f"\nCode received. Exchanging for token...", flush=True)
r = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
    "code": auth_code[0], "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
})
if r.status_code != 200:
    print(f"ERROR: {r.status_code} {r.text}", flush=True)
    exit(1)

tok = r.json()
td = {
    "token": tok["access_token"],
    "refresh_token": tok.get("refresh_token", ""),
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
    "scopes": SCOPES,
    "expiry": (__import__("datetime").datetime.now(__import__("datetime").UTC) +
               __import__("datetime").timedelta(seconds=tok.get("expires_in", 3600))).isoformat() + "Z",
}
print(f"Access: {tok['access_token'][:20]}... Refresh: {tok.get('refresh_token','')[:10]}...", flush=True)

tmp = os.path.join(tempfile.gettempdir(), "goog_oauth_https.json")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(td, f, ensure_ascii=False)
print(os.popen(f'gcloud secrets versions add google-oauth-token --data-file="{tmp}" --project=coherence-ominichannel-fs').read())
os.unlink(tmp)
print("DONE!", flush=True)
