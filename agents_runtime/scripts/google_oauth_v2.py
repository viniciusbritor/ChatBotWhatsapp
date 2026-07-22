"""Interactive Google OAuth v2 - gera token com escopos de Calendar + Drive + Gmail."""
import json
import os
import tempfile
import webbrowser
import requests
import urllib.parse

CLIENT_ID = "894828119087-goo6lcl6vgm5bdq5qgafscb8qbr4ueet.apps.googleusercontent.com"
CLIENT_SECRET = "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"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"

print("=" * 60)
print("GOOGLE OAUTH - GERAR TOKEN COM CALENDAR")
print("Projeto: coherence-ominichannel-fs")
print("=" * 60)

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

print(f"\nScopes: {', '.join(SCOPES)}")
print("\nAbrindo navegador para autorizacao...")
print("\nAPOS AUTORIZAR, o Google vai mostrar um CODIGO.")
print("Copie o CODIGO e cole aqui embaixo.\n")

webbrowser.open(auth_url)

auth_code = input("Cole o codigo de autorizacao: ").strip()
if not auth_code:
    print("Nenhum codigo fornecido.")
    exit(1)

print("\nTrocando code por token...")
r = requests.post("https://oauth2.googleapis.com/token", data={
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": auth_code,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
})

if r.status_code != 200:
    print(f"ERRO: {r.status_code} {r.text}")
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

print(f"\nAccess token obtido! (primeiros 20 chars): {tok['access_token'][:20]}...")
if tok.get("refresh_token"):
    print(f"Refresh token obtido! (primeiros 10 chars): {tok['refresh_token'][:10]}...")
else:
    print("⚠ SEM refresh token! O token expira em 1h.")

tmp = os.path.join(tempfile.gettempdir(), "google_oauth_calendar.json")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(token_data, f, ensure_ascii=False)

print("\nFazendo upload para GCP Secret Manager...")
result = os.popen(f'gcloud secrets versions add google-oauth-token --data-file="{tmp}" --project=coherence-ominichannel-fs').read()
print(result)
os.unlink(tmp)

print("✅ Token atualizado com sucesso!")
print("Execute para aplicar no Cloud Run:")
print("gcloud run services update agents-runtime-test --region=us-central1 --update-secrets='GOOGLE_OAUTH_TOKEN=google-oauth-token:latest'")
