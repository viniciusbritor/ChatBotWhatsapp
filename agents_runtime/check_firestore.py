from google.cloud import firestore

db = firestore.Client(project='coherence-ominichannel-fs')

print('=== Modules ===')
for doc in db.collection('modules').stream():
    d = doc.to_dict()
    print(f"  {doc.id}: {d.get('name')} -> {d.get('url')}")

print()
print('=== User Permissions (viniciusbritor) ===')
for doc in db.collection('user_permissions').where('user_email', '==', 'viniciusbritor@gmail.com').stream():
    d = doc.to_dict()
    print(f"  {doc.id}: module={d.get('module_id')} role={d.get('role')} active={d.get('is_active', d.get('is_approved'))}")

print()
print('=== Users ===')
for doc in db.collection('users').where('email', '==', 'viniciusbritor@gmail.com').stream():
    print(f"  {doc.id}: {doc.to_dict()}")
