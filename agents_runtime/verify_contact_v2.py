from google.cloud import firestore
import hashlib

db = firestore.Client(project='coherence-ominichannel-fs')
phone = '+5511966830020'
ph = hashlib.sha256(phone.encode()).hexdigest()[:16]

# Verificar contacts
print('=== Collection: contacts ===')
doc = db.collection('contacts').document(ph).get()
if doc.exists:
    print(f'  Encontrado: {doc.to_dict()}')
else:
    print('  NAO encontrado')

# Verificar todos os docs em contacts
print()
print('Todos os docs em contacts/:')
for d in db.collection('contacts').stream():
    print(f'  ID={d.id}: {d.to_dict()}')

# Verificar collections existentes
print()
print('Todas as collections:')
for c in db.collections():
    print(f'  {c.id}')
