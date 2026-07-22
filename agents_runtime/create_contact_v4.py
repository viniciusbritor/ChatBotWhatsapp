import hashlib
from google.cloud import firestore
from datetime import datetime, timezone

db = firestore.Client(project='coherence-ominichannel-fs')

# PHONE SEM o "+" (como o webhook Evolution extrai)
phone_no_plus = '5511966830020'
phone_with_plus = '+5511966830020'

ph_no_plus = hashlib.sha256(phone_no_plus.encode()).hexdigest()[:16]
ph_with_plus = hashlib.sha256(phone_with_plus.encode()).hexdigest()[:16]

now = datetime.now(timezone.utc).isoformat()

print(f"phone_com_+: {phone_with_plus} -> hash {ph_with_plus}")
print(f"phone_sem_+: {phone_no_plus} -> hash {ph_no_plus}")

contact_data = {
    'phone': phone_with_plus,
    'phone_hash': ph_no_plus,  # ID = phone_hash SEM o +
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
}

# Criar/update com ID = phone_hash SEM o +
contact_ref = db.collection('contacts').document(ph_no_plus)
contact_ref.set(contact_data, merge=True)
print(f"\nContato criado com ID correto: {ph_no_plus}")
print(f"Verificando: {contact_ref.get().to_dict().get('opted_in')}")
