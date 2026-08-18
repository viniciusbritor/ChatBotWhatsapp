from google.cloud import logging
import os
os.environ.setdefault('GCP_PROJECT', 'coherence-ominichannel-fs')
client = logging.Client(project='coherence-ominichannel-fs')
filter_str = '''resource.type="cloud_run_revision"
AND resource.labels.service_name="agents-runtime-test"
AND timestamp>="2026-08-17T01:40:00Z"'''
print('filter:', filter_str)
count = 0
for entry in client.list_entries(filter_=filter_str, page_size=500):
    payload = getattr(entry, 'payload', None) or {}
    if isinstance(payload, dict):
        msg = str(payload.get('message', ''))
    else:
        msg = str(payload)
    ts = entry.timestamp.isoformat()
    if any(k in msg.lower() for k in ['notify_admin', 'evolutiondel', 'solicitacao', 'evolution_http', 'send_text', 'evolution.coherenceai', '5511900000001', 'webhook']):
        print(f'{ts} | {msg[:300]}')
    count += 1
print(f'Total: {count}')