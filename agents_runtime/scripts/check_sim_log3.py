from google.cloud import logging
import os
os.environ.setdefault('GCP_PROJECT', 'coherence-ominichannel-fs')
client = logging.Client(project='coherence-ominichannel-fs')
# Buscar TODOS os logs do agents-runtime-test em 01:26 - agora
filter_str = '''resource.type="cloud_run_revision"
AND resource.labels.service_name="agents-runtime-test"
AND timestamp>="2026-08-17T01:26:40Z"
AND severity>=INFO'''
print('filter:', filter_str)
count = 0
notify_msgs = []
all_msgs = []
for entry in client.list_entries(filter_=filter_str, page_size=500):
    payload = getattr(entry, 'payload', None) or {}
    if isinstance(payload, dict):
        msg = str(payload.get('message', ''))
    else:
        msg = str(payload)
    ts = entry.timestamp.isoformat()
    all_msgs.append((ts, msg))
    count += 1
print(f'Total: {count}')
print()
print('=== All messages (filtered by notify_admin, send_text, evolution, admin) ===')
for ts, m in all_msgs:
    if any(k in m.lower() for k in ['notify_admin', 'send_text', 'evolution', 'admin', 'unapproved', 'access_request', 'solicitacao']):
        print(f'{ts} | {m[:300]}')