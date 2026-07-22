"""Interactive Google OAuth flow - generates token with Calendar + Drive + Gmail scopes."""
import json
import os
import tempfile
import webbrowser
import http.server
import urllib.parse
import requests
import time

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
        if auth_code:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorization received! You can close this window.")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code received.")
    def log_message(self, *a): pass

print("=" * 60)
print("GOOGLE OAUTH - GERAR TOKEN COM CALENDAR")
print("=" * 60)
print("\nAbrindo navegador para autorizacao...\n")
print(f"Scopes: {', '.join(SCOPES)}")
print("\nApos fazer login e autorizar, voce sera redirecionado")
print("para uma pagina em branco dizendo 'Authorization received!'")
print(f"\nAguardando redirecionamento em http://localhost:{REDIRECT_PORT}...\n")

webbrowser.open(auth_url)

server = http.server.HTTPServer(("localhost", REDIRECT_PORT), Handler)
timeout = time.time() + 120
while not auth_code and time.time() < timeout:
    server.handle_request()

if not auth_code:
    print("\nERRO: Nenhuma autorizacao recebida em 2 minutos.")
    exit(1)

print("\nCodigo de autorizacao recebido! Trocando por token...")

r = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": auth_code,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
})

if r.status_code != 200:
    print(f"\nERRO ao trocar code por token: {r.status_code} {r.text}")
    exit(1)

tok = r.json()
token_data = {
    "token": tok["access_token"],
    "refresh_token": tok.get("refresh_token", ""),
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scopes": SCOPES,
    "expiry": (__import__("datetime").datetime.now(__import__("datetime").UTC) +
               __import__("datetime").timedelta(seconds=tok.get("expires_in", 3600))).isoformat() + "Z",
}

print(f"Token obtido! Access token: {tok['access_token'][:20]}...")
print(f"Refresh token: {tok.get('refresh_token', 'NAO OBTIDO')[:10]}...")

if not tok.get("refresh_token"):
    print("\n⚠ Refresh token nao obtido! Isso significa que o token expira em 1h.")
    print("Para obter refresh token, execute novamente e authorize novamente.")
    choice = input("\nDeseja fazer upload mesmo assim? (s/N): ")
    if choice.lower() != 's':
        print("Abortado.")
        exit(0)

tmp = os.path.join(tempfile.gettempdir(), "google_oauth_final.json")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(token_data, f, ensure_ascii=False)

print("\nFazendo upload para GCP Secret Manager...")
result = os.popen(f'gcloud secrets versions add google-oauth-token --data-file="{tmp}" --project=coherence-ominichannel-fs').read()
print(result)
os.unlink(tmp)

input("\nPRESSIONE ENTER para finalizar o token refresh manual (se aplicavel)")
print("\n✅ Token atualizado com sucesso!")
print("Para aplicar no Cloud Run, execute manualmente:")
print("gcloud run services update agents-runtime-test --region=us-central1 --update-secrets='GOOGLE_OAUTH_TOKEN=google-oauth-token:latest'")
