#!/usr/bin/env python3
"""Script de Simulacao Headless de Mensagens WhatsApp.

Permite testar qualquer interacao de qualquer usuario (terceiro ou owner)
sem precisar enviar mensagens reais pelo WhatsApp.

Exemplo de uso:
    python scripts/simulate_user_chat.py --phone 5511992303650 --text "qual minha agenda de hoje?"
    python scripts/simulate_user_chat.py --phone 5511966830020 --text "lista meus arquivos do drive"
"""
import argparse
import asyncio
import json
import os
import sys

# Garante UTF-8 no terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Garante path raiz e GCP Project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")

from agent_orchestration.access_guardian import decide_guardian
from core.oauth_per_user import get_user_oauth, get_user_credentials
from pipelines.calendar_pipeline import run as run_calendar
from pipelines.doc_pipeline import run as run_drive
from pipelines.email_pipeline import run as run_email
from pipelines.jennifer_pipeline import run as run_jennifer


async def simulate(phone: str, text: str, pipeline_type: str = "auto", is_group: bool = False):
    print("=" * 60)
    print(f"🤖 SIMULAÇÃO WHATSAPP HEADLESS")
    print(f"📱 Usuário (Phone): {phone}")
    print(f"💬 Mensagem: \"{text}\"")
    print(f"👥 É Grupo?: {is_group}")
    print("=" * 60)

    # 1. Diagnóstico do Token OAuth
    token_data = get_user_oauth(phone)
    if token_data:
        scopes = token_data.get("scopes", [])
        print(f"✅ Token Google OAuth encontrado no Firestore: {len(scopes)} escopos concedidos.")
    else:
        print(f"⚠️ Nenhum token Google OAuth encontrado para {phone}.")

    # 2. Teste do Access Guardian
    print("\n[1/3] Avaliação de Permissão (Access Guardian)...")
    decision = decide_guardian(instance="Jennifer", phone=phone, capability="calendar.list_events")
    print(f"  • Verdict: {decision.verdict.upper()}")
    print(f"  • Reason: {decision.reason or 'N/A'}")
    if decision.oauth_link:
        print(f"  • Link OAuth: {decision.oauth_link}")

    # 3. Execução do Pipeline
    print(f"\n[2/3] Executando Pipeline ({pipeline_type})...")
    payload = {
        "phone": phone,
        "instance": "Jennifer",
        "text": text,
        "extra": {"is_group": is_group}
    }

    lowered = text.lower()
    if pipeline_type == "calendar" or any(w in lowered for w in ["agenda", "calendario", "compromisso", "reuniao"]):
        res = await run_calendar(payload)
    elif pipeline_type == "email" or any(w in lowered for w in ["email", "e-mail", "mensagem", "inbox"]):
        res = await run_email(payload)
    elif pipeline_type == "drive" or any(w in lowered for w in ["drive", "arquivo", "pasta", "documento"]):
        res = await run_drive(payload)
    else:
        res = await run_jennifer(payload)

    # 4. Resposta da Jennifer
    print("\n[3/3] Resposta da Jennifer:")
    print("-" * 60)
    print(res.get("reply", "Sem resposta"))
    print("-" * 60)
    if res.get("metadata"):
        print("Metadata:", json.dumps(res.get("metadata", {}), indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Simula mensagens WhatsApp para a Jennifer")
    parser.add_argument("--phone", required=True, help="Numero de telefone (ex: 5511992303650)")
    parser.add_argument("--text", required=True, help="Texto da mensagem enviada")
    parser.add_argument("--pipeline", default="auto", choices=["auto", "calendar", "email", "drive", "jennifer"], help="Pipeline a forcar")
    parser.add_argument("--group", action="store_true", help="Simular mensagem em grupo")

    args = parser.parse_args()
    asyncio.run(simulate(phone=args.phone, text=args.text, pipeline_type=args.pipeline, is_group=args.group))


if __name__ == "__main__":
    main()
