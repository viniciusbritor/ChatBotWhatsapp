"""Sync agent configs from data/agents/*.yaml to Firestore agents collection.

Runs on every deploy via cloudbuild-test.yaml. Upserts (merge=True) so
existing documents are updated, not overwritten. Idempotent.
"""
import os
import sys
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")

from google.cloud import firestore
from core.timezone import now_brt

YAML_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "agents")
REQUIRED_AGENTS = [
    "jennifier.yaml",
    "agent-knowledge-retriever.yaml",
    "agent-categorizer.yaml",
]


def load_yaml_agent(filename: str) -> dict:
    path = os.path.join(YAML_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    data["updated_at"] = now_brt().isoformat()
    if "instances" not in data:
        data["instances"] = ["jennifer"]
    data["enabled"] = True  # force enabled
    return data


def main():
    db = firestore.Client(project=os.getenv("GCP_PROJECT", "coherence-ominichannel-fs"))
    now = now_brt().isoformat()

    for filename in REQUIRED_AGENTS:
        agent = load_yaml_agent(filename)
        agent_id = agent.get("id")
        if not agent_id:
            print(f"SKIP {filename}: missing id field")
            continue

        agent["updated_at"] = now
        db.collection("agents").document(agent_id).set(agent, merge=True)
        print(f"SYNCED: {agent_id} (tools={agent.get('tools', [])})")

    # Also re-enable agent-knowledge-retriever explicitly (defense in depth)
    db.collection("agents").document("agent-knowledge-retriever").set(
        {"enabled": True, "updated_at": now}, merge=True
    )
    print("RE-ENABLED: agent-knowledge-retriever")

    print(f"Done. {len(REQUIRED_AGENTS)} agents synced to Firestore.")


if __name__ == "__main__":
    main()
