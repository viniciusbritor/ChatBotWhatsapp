"""Seed default agents, skills, and tools to Firestore."""
import sys

sys.path.insert(0, "C:/Users/vinic/workspace_antigravity/ChatBotWhatsapp/agents_runtime")

from google.cloud import firestore
from scripts.seed_initial_data import DEFAULT_AGENTS, DEFAULT_SKILLS, DEFAULT_TOOLS

db = firestore.Client(project='coherence-ominichannel-fs')

# Seed agents
print("=== Seeding 8 agents ===")
for agent in DEFAULT_AGENTS:
    ref = db.collection('agents').document(agent['id'])
    ref.set(agent)
    print(f"  Created agent: {agent['id']} ({agent['name']})")

# Seed skills
print("\n=== Seeding 4 skills ===")
for skill in DEFAULT_SKILLS:
    ref = db.collection('skills').document(skill['id'])
    ref.set(skill)
    print(f"  Created skill: {skill['id']} ({skill['name']})")

# Seed tools
print("\n=== Seeding 4 tools ===")
for tool in DEFAULT_TOOLS:
    ref = db.collection('tools').document(tool['id'])
    ref.set(tool)
    print(f"  Created tool: {tool['id']} ({tool['name']})")

print("\n=== Verifying counts ===")
print(f"  agents: {len(list(db.collection('agents').stream()))}")
print(f"  skills: {len(list(db.collection('skills').stream()))}")
print(f"  tools: {len(list(db.collection('tools').stream()))}")
