"""Smoke test do LinkedIn para detectar regressão do TIER 1.5 dispatch.

Por que este script existe:
- O user testou 12:42 GMT-3 ("busque meu perfil no linkedin") e a Jennifer
  alucinou "nao tenho acesso ao LinkedIn" em vez de chamar o manager-linkedin.
- Os logs mostraram `agent_id: manager-jennifier` (sem tools) em vez de
  `manager-linkedin` (com tools).
- O TIER 1.5 dispatch nunca foi invocado.
- Este script faz um POST direto no webhook do Cloud Run com payload
  realista para confirmar se o TIER 1.5 dispatch dispara.

Uso:
    python -m scripts.smoke_test_linkedin [--webhook URL] [--phone PHONE] [--text "..."]
    python -m scripts.smoke_test_linkedin  # usa defaults
"""
import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional


# Caminhos do gcloud no Windows.
GCLOUD_PATHS = [
    r"C:\Users\vinic\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    r"C:\Users\vinic\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.exe",
    "gcloud",
]


def get_webhook_url() -> str:
    """Obtem a URL do webhook do Cloud Run agents-runtime-test."""
    for gcloud in GCLOUD_PATHS:
        try:
            result = subprocess.run(
                [gcloud, "run", "services", "describe", "agents-runtime-test",
                 "--region=us-central1",
                 "--format=value(status.url)"],
                capture_output=True, text=True, check=True,
            )
            url = result.stdout.strip()
            if url:
                return url.rstrip("/") + "/webhook"
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError("Nao consegui obter a URL do webhook do Cloud Run.")


def get_access_token() -> str:
    """Obtem access token via gcloud."""
    for gcloud in GCLOUD_PATHS:
        try:
            result = subprocess.run(
                [gcloud, "auth", "print-access-token"],
                capture_output=True, text=True, check=True,
            )
            token = result.stdout.strip()
            if token:
                return token
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError:
            continue
    raise RuntimeError("Nao consegui obter access token do gcloud.")


def build_payload(
    phone: str,
    instance: str,
    text: str,
    remote_jid: str = None,
) -> Dict[str, Any]:
    """Constroi payload no formato Evolution webhook para o Cloud Run agents-runtime-test."""
    if remote_jid is None:
        remote_jid = f"{phone}@s.whatsapp.net"
    return {
        "event": "messages.upsert",
        "instance": instance,
        "data": {
            "key": {
                "remoteJid": remote_jid,
                "fromMe": False,
                "id": f"smoke-test-{int(time.time())}",
                "participant": remote_jid,
            },
            "pushName": "Smoke Test",
            "message": {"conversation": text},
            "messageType": "conversation",
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Smoke test do LinkedIn - POST direto no webhook",
    )
    parser.add_argument(
        "--webhook",
        help="URL do webhook (default: obtido do Cloud Run agents-runtime-test)",
    )
    parser.add_argument(
        "--phone",
        default="5511966830020",
        help="phone do user (default: 5511966830020 = Vinicius admin)",
    )
    parser.add_argument(
        "--instance",
        default="Jennifer",
        help="instance name (default: Jennifer)",
    )
    parser.add_argument(
        "--text",
        default="busque meu perfil no linkedin",
        help="texto a enviar (default: frase que revelou o bug do TIER 1.5)",
    )
    parser.add_argument(
        "--texts",
        nargs="*",
        help="lista de textos a enviar (se passar, sobrescreve --text)",
    )
    args = parser.parse_args()

    webhook = args.webhook or get_webhook_url()
    print("Webhook:", webhook)
    token = get_access_token()
    print("Token: OK")

    texts = args.texts if args.texts else [args.text]

    import requests
    for text in texts:
        payload = build_payload(args.phone, args.instance, text)
        print()
        print("--- POST text:", repr(text), "---")
        try:
            resp = requests.post(
                webhook,
                json=payload,
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                },
                timeout=60,
            )
            print("Status:", resp.status_code)
            print("Response:", resp.text[:500])
        except Exception as e:
            print("Erro:", e)
        time.sleep(2)

    print()
    print("--- Apos o smoke test, valide os logs: ---")
    print("  python -m scripts.logs --phone " + args.phone + " --since 5")
    print("  python -m scripts.logs --tier15 --since 5")
    print("  python -m scripts.logs --tier15-dispatch-failed --since 5")
    print("  python -m scripts.logs --observability-event --since 5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
