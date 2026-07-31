"""Smoke test for the unified access rule (RAG / Drive / Chat).

Manual, remote-only (Cloud Run test). Runs 4 scenarios against the
deployed `agents-runtime-test` service and logs the resolved
``intent`` and ``agent_id`` for each turn.

Usage:
    python scripts/smoke_access_rule.py
    python scripts/smoke_access_rule.py --base-url https://agents-runtime-test-XXX-uc.a.run.app
    python scripts/smoke_access_rule.py --phone 5511966830020 --sa-token "$AGENTS_RUNTIME_SA_TOKEN"

Each scenario sends a POST to ``/chat`` with a distinct message and
asserts (best-effort) the intent surfaced by the orchestrator. The
smoke prints a PASS/FAIL row per scenario; exits non-zero if any
scenario fails.

Scenarios:
1. RAG intent:  "quais documentos voce tem na sua base de conhecimento?"
2. Drive intent: "lista os arquivos do drive"
3. Drive in group (owner, confirmed): "lista os arquivos do drive" in
   a group where the owner has confirmed public sharing.
4. Chat:       "oi, tudo bem?"

Do NOT add this to CI. The script touches the live Cloud Run service
and requires a real SA token + at least one indexed document in
``agent-knowledge-v2`` for the RAG scenario to be meaningful.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


DEFAULT_BASE_URL = "https://agents-runtime-test-c5nbfc5meq-uc.a.run.app"
DEFAULT_PHONE = "5511966830020"
DEFAULT_SENDER = "Vini"
DEFAULT_INSTANCE = "jennifer"
DEFAULT_TIMEOUT_SEC = 30


SCENARIOS: list[Dict[str, Any]] = [
    {
        "id": "rag_private",
        "label": "RAG (base de conhecimento)",
        "text": "quais documentos voce tem na sua base de conhecimento?",
        "extra": {},
        "expect_any_intent": ["is_rag"],
        "reject_intent": ["is_drive"],
    },
    {
        "id": "drive_private",
        "label": "Drive (privado)",
        "text": "lista os arquivos do drive",
        "extra": {},
        "expect_intent": "is_drive",
    },
    {
        "id": "drive_group_consent",
        "label": "Drive em grupo (owner + confirmado)",
        "text": "lista os arquivos do drive",
        "extra": {
            "remote_jid": "120363401234567890@g.us",
            "is_group": True,
        },
        "expect_intent": "is_drive",
        "expect_metadata_pending_action": "group_consent",
    },
    {
        "id": "chat_memory",
        "label": "Chat memory (categoria default)",
        "text": "oi, tudo bem?",
        "extra": {},
        "reject_intent": ["is_rag", "is_drive", "is_email", "is_calendar"],
    },
]


def _post_chat(
    base_url: str,
    sa_token: str,
    instance: str,
    phone: str,
    sender: str,
    text: str,
    extra: Dict[str, Any],
    timeout_sec: int,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + "/chat"
    payload = {
        "instance": instance,
        "phone": phone,
        "sender_name": sender,
        "text": text,
        "extra": extra,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {sa_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return {
            "_http_status": exc.code,
            "_error": "http_error",
            "_raw": raw,
        }
    except urllib.error.URLError as exc:
        return {"_error": "url_error", "_reason": str(exc.reason)}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"_error": "invalid_json", "_raw": raw}
    data["_http_status"] = 200
    return data


def _check_scenario(scenario: Dict[str, Any], response: Dict[str, Any]) -> Tuple[bool, str]:
    if response.get("_error"):
        return False, f"transporte falhou: {response.get('_error')} | {response.get('_reason') or response.get('_raw')}"

    status = response.get("_http_status")
    if status is not None and status >= 400:
        return False, f"HTTP {status} | {response.get('_raw')}"

    metadata = response.get("metadata") or {}
    intent = metadata.get("intent") or {}
    blocked = bool(metadata.get("blocked"))
    pending_action = metadata.get("pending_action")

    if expect_intent := scenario.get("expect_intent"):
        if not intent.get(expect_intent):
            return False, f"intent.{expect_intent}=False (esperado True). intent={intent}"
    if expect_any := scenario.get("expect_any_intent"):
        if not any(intent.get(flag) for flag in expect_any):
            return False, (
                f"intent[{expect_any}] nenhum True. intent={intent}"
            )
    if reject := scenario.get("reject_intent"):
        leaked = [flag for flag in reject if intent.get(flag)]
        if leaked:
            return False, f"intent[{leaked}] nao deveria ser True. intent={intent}"
    if expect_pa := scenario.get("expect_metadata_pending_action"):
        if pending_action != expect_pa:
            return False, (
                f"metadata.pending_action={pending_action!r} "
                f"(esperado {expect_pa!r}). metadata={metadata}"
            )
    if blocked and not scenario.get("expect_metadata_pending_action"):
        return False, f"bloqueado sem pending_action esperada. metadata={metadata}"
    return True, f"intent={intent} | agent={metadata.get('agent_id')} | pending={pending_action}"


def _run(base_url: str, sa_token: str, instance: str, phone: str, sender: str, timeout_sec: int) -> int:
    print(f"[smoke_access_rule] base_url={base_url} instance={instance} phone={phone}")
    print(f"[smoke_access_rule] timeout={timeout_sec}s")
    print()
    failures = 0
    for scenario in SCENARIOS:
        print(f"-- {scenario['id']} | {scenario['label']}")
        response = _post_chat(
            base_url=base_url,
            sa_token=sa_token,
            instance=instance,
            phone=phone,
            sender=sender,
            text=scenario["text"],
            extra=scenario.get("extra") or {},
            timeout_sec=timeout_sec,
        )
        ok, msg = _check_scenario(scenario, response)
        marker = "PASS" if ok else "FAIL"
        print(f"   {marker} | {msg}")
        if not ok:
            failures += 1
            print(f"   response={json.dumps(response, ensure_ascii=False, default=str)[:500]}")
        time.sleep(0.5)
    print()
    if failures:
        print(f"[smoke_access_rule] {failures} de {len(SCENARIOS)} cenarios falharam.")
        return 1
    print(f"[smoke_access_rule] OK | {len(SCENARIOS)}/{len(SCENARIOS)} cenarios passaram.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test da regra unificada de acesso a conhecimento (RAG / Drive / Chat).",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("AGENTS_RUNTIME_BASE_URL", DEFAULT_BASE_URL),
        help="URL base do agents-runtime-test (default: %(default)s).",
    )
    parser.add_argument(
        "--sa-token",
        default=os.getenv("AGENTS_RUNTIME_SA_TOKEN", ""),
        help="Bearer SA token. Ler de env AGENTS_RUNTIME_SA_TOKEN se vazio.",
    )
    parser.add_argument("--instance", default=DEFAULT_INSTANCE)
    parser.add_argument("--phone", default=DEFAULT_PHONE)
    parser.add_argument("--sender", default=DEFAULT_SENDER)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC)
    args = parser.parse_args(argv)

    if not args.sa_token:
        print("ERRO: --sa-token nao foi informado e AGENTS_RUNTIME_SA_TOKEN nao esta setado.", file=sys.stderr)
        return 2

    return _run(
        base_url=args.base_url,
        sa_token=args.sa_token,
        instance=args.instance,
        phone=args.phone,
        sender=args.sender,
        timeout_sec=args.timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
