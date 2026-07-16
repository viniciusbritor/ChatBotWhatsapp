"""Fix BOM in serper-api-key secret."""
import os, json, urllib.request

PROJECT = "coherence-ominichannel-fs"
SECRET = "serper-api-key"

token = os.popen("gcloud auth print-access-token").read().strip()

url = f"https://secretmanager.googleapis.com/v1/projects/{PROJECT}/secrets/{SECRET}/versions/1:access"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
b64 = data["payload"]["data"]

raw = __import__('base64').b64decode(b64)
if raw[:3] == b'\xef\xbb\xbf':
    raw = raw[3:]
    print(f"BOM stripped, clean len: {len(raw)}")
else:
    print(f"No BOM, len: {len(raw)}")

tmp = os.path.join(os.environ["TEMP"], "serper_clean.txt")
with open(tmp, "wb") as f:
    f.write(raw)

cmd = f'gcloud secrets versions add {SECRET} --data-file="{tmp}" --project={PROJECT}'
print(os.popen(cmd).read())
os.unlink(tmp)
