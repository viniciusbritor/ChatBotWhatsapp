import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import firestore

from core.rag import EMBEDDING_DIM, EMBEDDING_MODEL, SCHEMA_VERSION, SHARED_COLLECTION

project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT", "coherence-ominichannel-fs")
database = firestore.Client(project=project)
documents = list(database.collection(SHARED_COLLECTION).limit(3).stream())
for document in documents:
    data = document.to_dict()
    vector = data.get("vector_embedding")
    print(
        f"doc_id={document.id} "
        f"model={data.get('embedding_model')} "
        f"dimension={len(vector) if vector else 0} "
        f"schema={data.get('schema_version')} "
        f"valid={bool(vector) and len(vector) == EMBEDDING_DIM and data.get('embedding_model') == EMBEDDING_MODEL and data.get('schema_version') == SCHEMA_VERSION}"
    )
print(f"collection={SHARED_COLLECTION} sampled={len(documents)}")
