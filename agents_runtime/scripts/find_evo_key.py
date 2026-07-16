import sqlite3
import os

dbs = [
    r"C:\Users\vinic\brasil_ai.db",
    r"C:\Users\vinic\workspace_antigravity\EvolutionWhatsapp\whatsapp-agente\agente\whatsapp_agente.db",
]

for db_path in dbs:
    if not os.path.exists(db_path):
        print(f"Not found: {db_path}")
        continue
    print(f"\n=== {db_path} ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT key, substr(value, 1, 20) as preview FROM secrets WHERE key LIKE '%evo%' OR key LIKE '%evolution%' OR key LIKE '%api_key%'")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"  Tables: {tables}")
    conn.close()
