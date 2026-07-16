"""Create OAuth client for coherence-ominichannel-fs and run OAuth flow."""
import json, os, tempfile, webbrowser, http.server, urllib.parse, requests, time, base64

PROJECT = "coherence-ominichannel-fs"
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

token = os.popen("gcloud auth print-access-token").read().strip()

# Step 1: Create a Desktop OAuth client
print("Creating OAuth client...")
client_data = {
    "displayName": "calendar-cli",
    "clientType": "DESKTOP",
    "redirectUris": ["http://localhost:8088"],
}
create_url = f"https://oauth2.googleapis.com/v1/projects/{PROJECT}/oauthClients"
r = requests.post(create_url, json=client_data, headers={
    "Authorization": f"Bearer {token}", "Content-Type": "application/json"})

if r.status_code == 200:
    client = r.json()
    print(f"OAuth client created!")
elif r.status_code == 409:
    # Already exists, find it
    print("Client may already exist...")
else:
    print(f"Error creating client: {r.status_code}")
    print(r.text)

# Try to list existing clients
print("\nListing OAuth clients...")
list_url = f"https://oauth2.googleapis.com/v1/projects/{PROJECT}/oauthClients"
r = requests.get(list_url, headers={"Authorization": f"Bearer {token}"})
if r.status_code == 200:
    clients = r.json().get("oauthClients", [])
    print(f"Existing OAuth clients:")
    for c in clients:
        print(f"  - {c.get('displayName')}: {c.get('name')}")
else:
    print(f"Error listing: {r.status_code} {r.text[:200]}")
