import requests
import json
import datetime
import tempfile
import os
data = json.load(open(r'C:\Users\vinic\.gemini\config\skills\google_calendar_manager\resources\token_drive.json'))
r = requests.post('https://oauth2.googleapis.com/token', data={
    'client_id': data['client_id'],
    'client_secret': data['client_secret'],
    'refresh_token': data['refresh_token'],
    'grant_type': 'refresh_token',
})
tok = r.json()
data['token'] = tok['access_token']
data['expiry'] = (datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=tok.get('expires_in', 3600))).isoformat() + 'Z'
tmp = os.path.join(tempfile.gettempdir(), 'google_oauth_clean.json')
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)
result = os.popen(f'gcloud secrets versions add google-oauth-token --data-file="{tmp}" --project=coherence-ominichannel-fs').read()
print(result)
os.unlink(tmp)
print('Done!')
