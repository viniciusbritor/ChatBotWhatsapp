from google.cloud import firestore
db = firestore.Client(project='coherence-ominichannel-fs')
docs = list(db.collection('public-Knowledge-Shared').limit(3).stream())
for d in docs:
    data = d.to_dict()
    emb = data.get('embedding', [])
    print(f"Doc: {d.id} | titulo: {data.get('titulo','')} | emb_len: {len(emb) if emb else 0} | keys: {list(data.keys())}")
print(f"Total docs: {len(docs)}")
