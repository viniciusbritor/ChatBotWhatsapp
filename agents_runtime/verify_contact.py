from google.cloud import firestore
import hashlib

db = firestore.Client(project='coherence-ominichannel-fs')
phone = '+5511966830020'
ph = hashlib.sha256(phone.encode()).hexdigest()[:16]
print(f'phone_hash esperado: {ph}')
print('Buscando por phone_hash...')
doc = db.collection('contatos').document(ph).get()
if doc.exists:
    d = doc.to_dict()
    print(f'  ENCONTRADO: opted_in={d.get("opted_in")}')
else:
    print('  NAO ENCONTRADO!')
print()
print('Todos os docs em contatos/:')
for d in db.collection('contatos').stream():
    dd = d.to_dict()
    print(f'  ID={d.id}: phone={dd.get("phone")} opted_in={dd.get("opted_in")}')
