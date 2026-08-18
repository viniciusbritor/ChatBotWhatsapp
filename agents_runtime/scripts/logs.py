"""Jennifer Logs CLI - ferramenta para ler logs do Cloud Run sem truncamento.

Por que esta ferramenta existe:
- gcloud logging read + --format value(...) trunca o conteudo (mostra so a chave)
- gcloud CLI quebra com filters complexos no PowerShell (caracteres = e :)
- Logs em Cloud Run podem ter ate 250KB; gcloud nem sempre mostra o conteudo completo

Esta ferramenta usa a REST API (logging.googleapis.com/v2/entries:list) diretamente,
com paginacao automatica e filtros ricos. Resolve definitivamente o problema de
truncamento dos logs para investigacao.

Uso:
    python -m scripts.logs --phone 5511966830020 --since 30
    python -m scripts.logs --manager linkedin --since 60
    python -m scripts.logs --tier15 --since 120
    python -m scripts.logs --tier15-keyword-gap --since 240
    python -m scripts.logs --errors-only --since 15
    python -m scripts.logs --text "buscar meu perfil" --since 60

Filtros (podem ser combinados):
    --phone         phone do user (ex: 5511966830020)
    --manager       manager_id (ex: manager-linkedin, manager-jennifier)
    --tier15        apenas logs do TIER 1.5 dispatch
    --errors-only   apenas severity ERROR
    --warnings-only apenas severity WARNING
    --since         minutos atras (default 30)
    --limit         maximo de entries (default 100)
    --text          filtra entries cujo jsonPayload.message contem o texto
    --observability-event  apenas observability_stage
    --tier15-keyword-gap   apenas tier15_keyword_gap
    --tier15-dispatch-failed  apenas tier15_dispatch_handler_failed
    --raw           saida em JSON bruto (default: formatado)
    --paginate      paginar todos os resultados (default: so primeira pagina)
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


# Caminhos do gcloud no Windows. No Linux/macOS, gcloud esta no PATH.
GCLOUD_PATHS = [
    r"C:\Users\vinic\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd",
    r"C:\Users\vinic\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.exe",
    "gcloud",
]


def get_access_token() -> str:
    """Obtem access token via gcloud auth print-access-token."""
    last_err = None
    for gcloud in GCLOUD_PATHS:
        try:
            result = subprocess.run(
                [gcloud, "auth", "print-access-token"],
                capture_output=True, text=True, check=True,
            )
            token = result.stdout.strip()
            if token:
                return token
        except FileNotFoundError as e:
            last_err = e
        except subprocess.CalledProcessError as e:
            last_err = e
    raise RuntimeError(
        f"Nao consegui obter access token do gcloud. Tentou: {GCLOUD_PATHS}. "
        f"Erro: {last_err}"
    )


def build_filter(
    phone=None,
    manager=None,
    tier15=False,
    errors_only=False,
    warnings_only=False,
    text=None,
    observability_event=False,
    tier15_keyword_gap=False,
    tier15_dispatch_failed=False,
    since_minutes=30,
):
    """Constroi o filter do Cloud Logging (sem caracteres = problematicos)."""
    parts = [
        'resource.type="cloud_run_revision"',
        'resource.labels.service_name="agents-runtime-test"',
    ]
    tz_brasilia = timezone(timedelta(hours=-3))
    cutoff = datetime.now(tz_brasilia) - timedelta(minutes=since_minutes)
    ts = cutoff.strftime("%Y-%m-%dT%H:%M:%S%%S-03:00")
    parts.append("timestamp>=" + ts)
    if errors_only:
        parts.append('severity=ERROR')
    elif warnings_only:
        parts.append('severity=WARNING')
    if manager:
        parts.append('jsonPayload.agent_id="' + manager + '"')
    if tier15:
        parts.append(
            '(jsonPayload.message="tier15_dispatch" OR '
            'jsonPayload.message="tier15_dispatch_handler_failed" OR '
            'jsonPayload.message="tier15_blocked" OR '
            'jsonPayload.message="tier15-not-found" OR '
            'jsonPayload.message="tier15_keyword_gap" OR '
            'jsonPayload.event_name="tier15")'
        )
    if observability_event:
        parts.append('jsonPayload.event_name="observability_stage"')
    if tier15_keyword_gap:
        parts.append('jsonPayload.message="tier15_keyword_gap"')
    if tier15_dispatch_failed:
        parts.append('jsonPayload.message="tier15_dispatch_handler_failed"')
    if phone:
        parts.append('jsonPayload.message:"' + phone + '"')
    if text:
        parts.append('jsonPayload.message:"' + text + '"')
    return " AND ".join(parts)


def fetch_entries(token, body, timeout=30):
    """Faz POST para a REST API do Cloud Logging."""
    import requests
    resp = requests.post(
        "https://logging.googleapis.com/v2/entries:list",
        json=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            "Cloud Logging API retornou " + str(resp.status_code) + ": " + resp.text[:500]
        )
    return resp.json().get("entries", [])


def fetch_all_entries_paginated(
    token, project, filter_str, page_size=100, max_entries=500, timeout=30
):
    """Faz paginacao automatica via nextPageToken."""
    entries = []
    page_token = None
    while len(entries) < max_entries:
        body = {
            "resourceNames": ["projects/" + project],
            "filter": filter_str,
            "orderBy": "timestamp DESC",
            "pageSize": page_size,
        }
        if page_token:
            body["pageToken"] = page_token
        result = fetch_entries(token, body, timeout=timeout)
        batch = result.get("entries", [])
        entries.extend(batch)
        page_token = result.get("nextPageToken")
        if not page_token or not batch:
            break
    return entries


def format_entry(entry, raw=False):
    """Formata uma entry do Cloud Logging para saida legivel."""
    if raw:
        return json.dumps(entry, indent=2, ensure_ascii=False, default=str)
    ts = entry.get("timestamp", "")
    sev = entry.get("severity", "")
    p = entry.get("jsonPayload", {})
    msg = p.get("message", "")
    structured_keys = [
        "agent_id", "toolkit", "manager", "stage",
        "duration_ms", "tool", "toolkit_slug", "exc",
    ]
    structured = {k: p[k] for k in structured_keys if k in p}
    parts = ["[" + ts + "]", "(" + sev + ")"]
    if structured:
        parts.append(json.dumps(structured, ensure_ascii=False, default=str))
    parts.append(msg[:300])
    return " ".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Jennifer Logs CLI - ler logs do Cloud Run sem truncamento",
    )
    parser.add_argument("--phone", help="phone do user (ex: 5511966830020)")
    parser.add_argument("--manager", help="manager_id (ex: manager-linkedin)")
    parser.add_argument("--tier15", action="store_true",
                        help="apenas logs do TIER 1.5 dispatch")
    parser.add_argument("--tier15-keyword-gap", action="store_true",
                        help="apenas tier15_keyword_gap (C1)")
    parser.add_argument("--tier15-dispatch-failed", action="store_true",
                        help="apenas tier15_dispatch_handler_failed (C2)")
    parser.add_argument("--errors-only", action="store_true", help="apenas ERROR")
    parser.add_argument("--warnings-only", action="store_true",
                        help="apenas WARNING")
    parser.add_argument("--text", help="filtra entries com texto especifico")
    parser.add_argument("--observability-event", action="store_true",
                        help="apenas observability_stage")
    parser.add_argument("--since", type=int, default=30, help="minutos atras")
    parser.add_argument("--limit", type=int, default=100, help="max entries")
    parser.add_argument("--paginate", action="store_true",
                        help="paginar todos os resultados")
    parser.add_argument("--raw", action="store_true", help="saida JSON bruta")
    parser.add_argument("--project", default="coherence-ominichannel-fs",
                        help="GCP project ID")
    args = parser.parse_args()

    if not any([
        args.phone, args.manager, args.tier15, args.tier15_keyword_gap,
        args.tier15_dispatch_failed, args.errors_only, args.warnings_only,
        args.text, args.observability_event,
    ]):
        parser.print_help()
        print("\nErro: forneca pelo menos um filtro (--phone, --manager, --tier15, etc.)",
              file=sys.stderr)
        return 1

    token = get_access_token()
    filter_str = build_filter(
        phone=args.phone,
        manager=args.manager,
        tier15=args.tier15,
        errors_only=args.errors_only,
        warnings_only=args.warnings_only,
        text=args.text,
        observability_event=args.observability_event,
        tier15_keyword_gap=args.tier15_keyword_gap,
        tier15_dispatch_failed=args.tier15_dispatch_failed,
        since_minutes=args.since,
    )

    page_size = min(args.limit, 500)
    if args.paginate:
        entries = fetch_all_entries_paginated(
            token=token, project=args.project, filter_str=filter_str,
            page_size=page_size, max_entries=args.limit,
        )
    else:
        body = {
            "resourceNames": ["projects/" + args.project],
            "filter": filter_str,
            "orderBy": "timestamp DESC",
            "pageSize": page_size,
        }
        result = fetch_entries(token, body)
        entries = result.get("entries", [])

    print("=== Total entries: " + str(len(entries)) + " ===", file=sys.stderr)
    for e in entries:
        print(format_entry(e, raw=args.raw))
    return 0


if __name__ == "__main__":
    sys.exit(main())
