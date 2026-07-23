"""Diagnostic probe against the live Evolution API.

We hit the actual endpoint shapes used by core/evolution_client.py
to find out *exactly* which one returns 4xx.
"""
import asyncio

import httpx
from google.cloud import secretmanager


def _key() -> str:
    sm = secretmanager.SecretManagerServiceClient()
    return sm.access_secret_version(
        request={"name": "projects/coherence-ominichannel-fs/secrets/evolution-api-key/versions/latest"}
    ).payload.data.decode().strip()


async def main() -> None:
    api_key = _key()
    base = "https://evolution.coherenceai.com.br"
    headers = {"apikey": api_key, "Content-Type": "application/json"}
    print("token:", api_key[:4] + "..." + api_key[-2:], "len", len(api_key))
    async with httpx.AsyncClient(timeout=15) as client:
        for method, path, body in [
            ("GET", "/instance/fetchInstances", None),
            ("GET", "/instance/connectionState/jennifer", None),
            ("POST", "/message/sendText/jennifer", {"number": "5511966830020", "text": "teste diags"}),
            ("GET", "/chat/findMessages/jennifer", None),
            ("POST", "/chat/markMessageAsRead/jennifer", {"messages": [{"id": "DIAG", "fromMe": False, "remoteJid": "5511966830020@s.whatsapp.net"}]}),
        ]:
            r = await client.request(method, base + path, headers=headers, json=body)
            print(f"{method} {path} -> {r.status_code}: {r.text[:200]}")


asyncio.run(main())
