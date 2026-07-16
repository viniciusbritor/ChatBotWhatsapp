"""Google OAuth interactivo - servidor local na porta 8088."""
import json, os, tempfile, webbrowser, http.server, urllib.parse, requests, time, threading

CLIENT_ID = "894828119087-goo6lcl6vgm5bdq5qgafscb8qbr4ueet.apps.googleusercontent.com"
CLIENT_SECRET = "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"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
REDIRECT_PORT = 8088
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"

auth_url = (
    "https://accounts.google.com/o/oauth2/auth?"
    + urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
    })
)

auth_code = None

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        if auth_code:
            self.wfile.write(b"OK - pode fechar esta janela.")
        else:
            self.wfile.write(b"Erro - sem codigo.")
    def log_message(self, *a): pass

print("=" * 60)
print("GOOGLE OAUTH - GERAR TOKEN")
print("Projeto: coherence-ominichannel-fs")
print("=" * 60)
print(f"\nAbrindo navegador... Autorize as permissoes.")
print(f"\nScopes: Calendar + Drive + Gmail\n")

server = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

webbrowser.open(auth_url)

time.sleep(30)

if auth_code:
    print(f"\nCode recebido! Trocando por token...")
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "code": auth_code, "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
    })
    if r.status_code != 200:
        print(f"ERRO: {r.status_code} {r.text}")
        exit(1)
    tok = r.json()
    td = {
        "token": tok["access_token"],
        "refresh_token": tok.get("refresh_token", ""),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "scopes": SCOPES,
        "expiry": (datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=tok.get("expires_in", 3600))).isoformat() + "Z",
    }
    tmp = os.path.join(tempfile.gettempdir(), "google_oauth_calendar.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(td, f, ensure_ascii=False)
    print(os.popen(f'gcloud secrets versions add google-oauth-token --data-file="{tmp}" --project=coherence-ominichannel-fs').read())
    os.unlink(tmp)
    print("✅ Token atualizado!")
else:
    print("Nenhum code recebido em 30s. Verifique se a URL foi aberta corretamente.")
    print(f"\nURL manual:\n{auth_url}")

import datetime
