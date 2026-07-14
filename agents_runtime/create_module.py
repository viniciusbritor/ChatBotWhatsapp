from google.cloud import firestore
from datetime import datetime, timezone

db = firestore.Client(project='coherence-ominichannel-fs')

module_data = {
    'id': 'omnichannel-agentes',
    'name': 'Agentes Omnichannel',
    'url': 'https://agents-runtime-test-c5nbfc5meq-uc.a.run.app',
    'description': 'Runtime multi-agente (Jennifer + 4 Managers + 3 Specialists). Edite skills/tools sem rebuild.',
    'icon': 'Bot',
    'instances': ['jennifer'],
    'enabled': True,
    'created_at': datetime.now(timezone.utc).isoformat(),
    'updated_at': datetime.now(timezone.utc).isoformat(),
    'updated_by': 'viniciusbritor@gmail.com',
}

ref = db.collection('modules').document('omnichannel-agentes')
ref.set(module_data)
print('Module registered:', ref.get().to_dict())
