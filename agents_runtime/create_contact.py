from google.cloud import firestore
from datetime import datetime, timezone

db = firestore.Client(project='coherence-ominichannel-fs')

phone = '+5511966830020'
now = datetime.now(timezone.utc).isoformat()

contact_ref = db.collection('contatos').document(phone)
contact_ref.set({
    'phone': phone,
    'phone_hash': 'master_user',
    'opted_in': True,
    'opted_in_at': now,
    'first_seen': now,
    'last_msg_at': now,
    'msgs_this_hour': 0,
    'msgs_today': 0,
    'msgs_this_week': 0,
    'proactive_mode': 'normal',
    'proactive_eligible': True,
    'proactive_messages_today': 0,
    'proactive_messages_this_week': 0,
    'proactive_cooldown_until': None,
    'proactive_paused_until': None,
    'display_name': 'Vinicius',
    'preferred_name': 'Vini',
    'created_at': now,
    'updated_at': now,
}, merge=True)

print('Contato criado:', contact_ref.get().to_dict())
