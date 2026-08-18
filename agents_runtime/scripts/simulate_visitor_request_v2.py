"""Simulação real: visitante pede acesso, admin recebe link.

Cenário:
1. Visitante (novo phone fictício) fala com a Jennifer pedindo acesso
2. Orchestrator classifica intent = "ferramentas" (email)
3. Pipeline email dispara check_google_access
4. Visitor eh guest (sem OAuth, sem aprovacao)
5. notify_admin_access_request gera link HMAC SHA-256
6. Admin (Vinicius, 5511966830020) recebe link no WhatsApp
"""
import os
import asyncio
import sys
import requests
import json
import io
import datetime

# Force UTF-8 for stdout (Windows cp1252 doesn't render emojis)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

os.environ.setdefault("GCP_PROJECT", "coherence-ominichannel-fs")

VISITOR_PHONE = "5511988776655"
ADMIN_PHONE = "5511966830020"
WEBHOOK_URL = "https://agents-runtime-test-894828119087.southamerica-east1.run.app/webhook"

print("=" * 80)
print(f"SIMULACAO: VISITANTE {VISITOR_PHONE} PEDE ACESSO")
print("=" * 80)
print()

# PASSO 1: Limpar visitante anterior
print(">>> PASSO 1: Limpar visitante de teste anterior")
print("-" * 80)
from google.cloud import firestore
db = firestore.Client(project="coherence-ominichannel-fs")
doc = db.collection("usuarios").document(VISITOR_PHONE).get()
if doc.exists:
    db.collection("usuarios").document(VISITOR_PHONE).delete()
    print(f"  Visitante {VISITOR_PHONE} removido (clean slate).")
else:
    print(f"  Visitante {VISITOR_PHONE} nao existe. Continuando...")
print()

# PASSO 2: Enviar webhook
print(">>> PASSO 2: Enviar webhook WhatsApp -> Orchestrator")
print("-" * 80)
webhook_payload = {
    "event": "messages.upsert",
    "instance": "Jennifer",
    "data": {
        "key": {
            "remoteJid": f"{VISITOR_PHONE}@s.whatsapp.net",
            "fromMe": False,
            "id": f"SIM_LIB_{int(datetime.datetime.now().timestamp())}"
        },
        "pushName": "Maria Silva Teste",
        "message": {
            "conversation": "oi, queria ver meus emails nao lidos na gmail"
        },
        "messageType": "conversation",
        "messageTimestamp": int(datetime.datetime.now().timestamp()),
        "instanceId": "2e0b001f-3ace-4576-a1ea-bcbb4d6e664c",
        "source": "android"
    },
    "sender": f"{VISITOR_PHONE}@s.whatsapp.net",
    "destination": f"{VISITOR_PHONE}@s.whatsapp.net",
    "date_time": datetime.datetime.now().isoformat(),
    "server_url": "https://evolution.example.com",
    "apikey": "test"
}

print(f"  Payload:")
print(f"    Phone: {VISITOR_PHONE}")
print(f"    Nome: Maria Silva Teste")
print(f"    Mensagem: 'oi, queria ver meus emails nao lidos na gmail'")
print(f"    Endpoint: {WEBHOOK_URL}")
print()
print(f"  Enviando...")
response = requests.post(WEBHOOK_URL, json=webhook_payload, timeout=30)
print(f"  Resposta: {response.status_code} {response.text}")
print()

# PASSO 3: Aguardar
print(">>> PASSO 3: Aguardar orchestrator processar (30s)")
print("-" * 80)
import time
print(f"  Aguardando 30 segundos...")
time.sleep(30)
print(f"  OK: Verificando estado...")
print()

# PASSO 4: Verificar estado
print(">>> PASSO 4: Verificar estado do visitante APOS webhook")
print("-" * 80)
doc = db.collection("usuarios").document(VISITOR_PHONE).get()
if doc.exists:
    data = doc.to_dict()
    print(f"  Dados do visitante {VISITOR_PHONE}:")
    for k in ["phone", "name", "role", "is_approved", "approved_by", "google_oauth_token"]:
        v = data.get(k)
        if isinstance(v, dict):
            v = f"{{...{len(v)} keys...}}"
        print(f"    {k}: {v}")
else:
    print(f"  Visitante nao foi registrado")
print()

# PASSO 5: Gerar link
print(">>> PASSO 5: Gerar link de aprovacao (preview do que admin receberia)")
print("-" * 80)
from core.admin_notify import generate_approval_url, create_approval_token
token = create_approval_token(VISITOR_PHONE)
url = generate_approval_url(VISITOR_PHONE)
print(f"  Token HMAC SHA-256:")
print(f"    {token[:60]}...")
print(f"    {token[-40:]}")
print()
print(f"  URL completa de aprovacao:")
print(f"    {url}")
print()

# PASSO 6: Mostrar mensagem que SERIA enviada
print(">>> PASSO 6: Mensagem que o admin (Vinicius) receberia no WhatsApp")
print("-" * 80)
print(f"  >>> FROM: Jennifer")
print(f"  >>> TO: 5511966830020 (Vinicius)")
print(f"  >>> TYPE: Solicitacao de Acesso")
print()

# Montar a mensagem (igual ao que core.admin_notify monta)
name_display = "Maria Silva Teste"
message_text = "oi, queria ver meus emails nao lidos na gmail"
msg = (
    f"🔔 *Solicitacao de Acesso a Jennifer*\n\n"
    f"👤 *Nome:* {name_display}\n"
    f"📱 *Telefone:* +{VISITOR_PHONE}\n"
    f"💬 *Mensagem:* \"{message_text}\"\n\n"
    f"Para liberar como *Analista*:\n"
    f"👉 {url}\n\n"
    f"_Aguardando sua decisao. Link expira em 30 dias._"
)

print("  ┌──────────────────────────────────────────────────────────────┐")
for line in msg.split("\n"):
    print(f"  │ {line.ljust(62)} │")
print("  └──────────────────────────────────────────────────────────────┘")
print()

# PASSO 7: Verificar logs do Cloud Run
print(">>> PASSO 7: Verificar logs do Cloud Run (notify_admin_access_request)")
print("-" * 80)
print("  Buscando logs...")
import subprocess
result = subprocess.run(
    [
        "gcloud", "--project=coherence-ominichannel-fs", "logging", "read",
        f"resource.type=cloud_run_revision AND resource.labels.service_name=agents-runtime-test AND textPayload:{VISITOR_PHONE}",
        "--limit=20", "--format=json", "--freshness=10m",
    ],
    capture_output=True, text=True, timeout=60
)
try:
    logs = json.loads(result.stdout) if result.stdout.strip() else []
    print(f"  Encontrados: {len(logs)} logs")
    for log in logs[:10]:
        ts = log.get("timestamp", "?")
        payload = log.get("textPayload", "") or log.get("jsonPayload", {}).get("message", "")
        print(f"    [{ts}] {payload[:200]}")
except Exception as exc:
    print(f"  Erro ao parsear logs: {exc}")
    print(f"  Stdout: {result.stdout[:500]}")
print()

print("=" * 80)
print("SIMULACAO CONCLUIDA")
print("=" * 80)
print()
print("ACAO DO ADMIN (VOCE - Vinicius):")
print(f"  1. Abre o WhatsApp (celular)")
print(f"  2. Ve a notificacao acima")
print(f"  3. Clica no link OU abre no browser:")
print(f"     {url}")
print(f"  4. Tela de confirmacao aparece (botao 'Confirmar e Liberar Acesso')")
print(f"  5. Apos clicar: visitante vira 'analyst' com is_approved=True")
print()
print("POS-VINCULACAO:")
print(f"  - Welcome message eh enviada para {VISITOR_PHONE}")
print(f"  - User pode refazer OAuth Google e passar a usar")
print()
print(">>> VALIDAR NOS LOGS DO CLOUD RUN <<<")
print("    gcloud --project=coherence-ominichannel-fs logging read \\")
print(f"      'resource.type=cloud_run_revision AND textPayload:{VISITOR_PHONE}' \\")
print("      --limit=20 --freshness=10m")