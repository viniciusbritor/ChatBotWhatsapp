"""Backfill: registra tools locomotion/weather/youtube no Firestore e
atualiza o agente jennifier com as novas tools + system_prompt (PT10).

Rode apos o deploy quando o seed_default_data nao roda (cache ja
populado):  python -m scripts.backfill_tools_jennifier
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import firestore  # noqa: E402

from scripts.seed_initial_data import DEFAULT_AGENTS, DEFAULT_TOOLS  # noqa: E402


def main() -> int:
    project = os.getenv("GCP_PROJECT") or os.getenv("GCLOUD_PROJECT") or "coherence-ominichannel-fs"
    db = firestore.Client(project=project)

    # 1) Registrar tools que nao existem (merge)
    existing_tool_ids = {d.id for d in db.collection("tools").stream()}
    created = 0
    for tool in DEFAULT_TOOLS:
        if tool["id"] not in existing_tool_ids:
            db.collection("tools").document(tool["id"]).set(tool, merge=True)
            created += 1
    print(f"tools criadas: {created}")

    # 2) Atualizar o agente jennifier com tools + system_prompt
    jennifier = next(a for a in DEFAULT_AGENTS if a["id"] == "jennifier")
    ref = db.collection("agents").document("jennifier")
    doc = ref.get()
    if not doc.exists:
        print("ERRO: agents/jennifier nao existe")
        return 1
    ref.set({
        "tools": jennifier["tools"],
        "system_prompt": jennifier["system_prompt"],
        "system_prompt_version": 4,
        "updated_at": __import__("core.timezone", fromlist=["now_brt"]).now_brt().isoformat(),
    }, merge=True)
    print("agents/jennifier atualizado (tools + system_prompt v4)")

    # 3) Forcar reload remoto via admin (force_reload e endpoint interno;
    # aqui apenas sinalizamos)
    print("done. Reinicie a instancia ou aguarde o AGENT_RELOAD_INTERVAL_SEC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
