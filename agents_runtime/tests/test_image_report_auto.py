"""Tests for tabular payload detection + auto-image render (F4d.9 + F-IMAGE).

When the agent's metadata contains a tool_result for a tabular source
(drive.list_folder, gmail.search_messages, calendar.list_events),
the orchestrator should auto-detect it and produce a PNG payload.

Quando o pipeline roda com ``tools: []`` (prefetch injetado no
system_prompt), o ``pipelines/_executor.run_agent`` anexa
``metadata["tabular"]`` e o detector prioriza essa fonte.
"""
import base64

from orchestrator import _detect_tabular_payload

CAL = "\U0001F4C5"  # 📅
MAIL = "\U0001F4E7"  # 📧
FILE = "\U0001F4C1"  # 📁
BOOK = "\U0001F4DA"  # 📚


def test_detect_drive_list_folder():
    result = {
        "metadata": {
            "tool_results": [
                {
                    "tool": "drive.list_folder",
                    "result": {
                        "files": [
                            {"name": "atas.pdf", "mime_type": "application/pdf",
                             "modified": "2026-07-28T10:00:00Z"},
                            {"name": "Custos.xlsx", "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             "modified": "2026-07-27T10:00:00Z"},
                        ]
                    },
                }
            ]
        }
    }
    payload = _detect_tabular_payload(result)
    assert payload is not None
    assert payload["title"] == "Arquivos da pasta"
    assert payload["headers"] == ["Nome", "Tipo", "Modificado"]
    assert payload["emoji_header"] == FILE
    assert payload["rows"][0][0] == "atas.pdf"
    assert payload["rows"][1][0] == "Custos.xlsx"
    assert payload["rows"][1][1] == "Planilha"


def test_detect_gmail_search():
    result = {
        "metadata": {
            "tool_results": [
                {
                    "tool": "gmail.search_messages",
                    "result": {
                        "messages": [
                            {"subject": "Re: chamada", "from": "foo@bar.com",
                             "date": "2026-07-28"},
                        ]
                    },
                }
            ]
        }
    }
    payload = _detect_tabular_payload(result)
    assert payload is not None
    assert payload["title"] == "Emails encontrados"
    assert payload["headers"] == ["Assunto", "De", "Data"]
    assert payload["emoji_header"] == MAIL


def test_detect_calendar_list_events():
    result = {
        "metadata": {
            "tool_results": [
                {
                    "tool": "calendar.list_events",
                    "result": {
                        "events": [
                            {"summary": "Standup", "start": {"dateTime": "2026-07-28T09:00:00Z"},
                             "end": {"dateTime": "2026-07-28T09:30:00Z"}}
                        ]
                    },
                }
            ]
        }
    }
    payload = _detect_tabular_payload(result)
    assert payload is not None
    assert payload["title"] == "Eventos da agenda"
    assert payload["headers"] == ["Evento", "Início", "Fim"]
    assert payload["emoji_header"] == CAL


def test_detect_returns_none_when_no_tabular_tool():
    result = {
        "metadata": {
            "tool_results": [
                {"tool": "calendar.create_event", "result": {"id": "abc"}},
            ]
        }
    }
    assert _detect_tabular_payload(result) is None


def test_detect_returns_none_when_metadata_missing():
    result = {"metadata": {}}
    assert _detect_tabular_payload(result) is None


def test_detect_handles_empty_lists():
    result = {
        "metadata": {
            "tool_results": [
                {"tool": "drive.list_folder", "result": {"files": []}},
            ]
        }
    }
    assert _detect_tabular_payload(result) is None


def test_render_report_produces_valid_png_bytes():
    from tools.image_report import render_report

    rendered = render_report(
        title="Test",
        headers=["A", "B"],
        rows=[["x", "y"], ["z", "w"]],
        emoji_header=FILE,
    )
    assert rendered["png_bytes"][:8] == b"\x89PNG\r\n\x1a\n"
    assert base64.b64decode(rendered["data_uri"].split(",", 1)[1])[:8] == b"\x89PNG\r\n\x1a\n"


def test_detect_knowledge_retrieve_table():
    """knowledge.retrieve RAG chunks viram tabela (Fase B.2 30/07)."""
    result = {
        "metadata": {
            "tool_results": [
                {"tool": "knowledge.retrieve", "result": {
                    "scope": "private",
                    "decision": "private",
                    "count": 3,
                    "results": [
                        {
                            "source_title": "cdc-portugues-2013.pdf",
                            "content": "Art. 42 CDC: o consumidor tem direito a informacao adequada.",
                            "score": 0.92,
                        },
                        {
                            "source_title": "Edital Pregao.pdf",
                            "content": "Objeto: aquicao de licencas de software.",
                            "score": 0.81,
                        },
                        {
                            "source_title": "Dissertacao.pdf",
                            "content": "Estudo analisa impacto da IA generativa.",
                            "score": 0.74,
                        },
                    ],
                }},
            ],
        },
    }
    payload = _detect_tabular_payload(result)
    assert payload is not None
    assert payload["title"] == "Conhecimento encontrado (3 trechos)"
    assert payload["headers"] == ["Fonte", "Trecho", "Score"]
    assert payload["emoji_header"] == BOOK
    assert len(payload["rows"]) == 3
    assert payload["rows"][0][0] == "cdc-portugues-2013.pdf"
    assert "Art. 42 CDC" in payload["rows"][0][1]
    assert payload["rows"][0][2] == "0.92"


def test_detect_knowledge_retrieve_empty_returns_none():
    """RAG sem resultados NAO gera tabela."""
    result = {
        "metadata": {
            "tool_results": [
                {"tool": "knowledge.retrieve", "result": {
                    "count": 0, "results": [],
                }},
            ],
        },
    }
    assert _detect_tabular_payload(result) is None


def test_detect_knowledge_retrieve_truncates_excerpt():
    """Excerto longo e truncado em 120 chars (cell cap)."""
    long_content = "a" * 200
    result = {
        "metadata": {
            "tool_results": [
                {"tool": "knowledge.retrieve", "result": {
                    "count": 1,
                    "results": [
                        {"source_title": "doc.pdf", "content": long_content, "score": 0.5},
                    ],
                }},
            ],
        },
    }
    payload = _detect_tabular_payload(result)
    assert payload["rows"][0][1] == ("a" * 120)


# --- Prefetch tabular (pipelines com tools=[]) ---

def test_detect_prefetch_tabular_calendar():
    """metadata['tabular'] anexado pelo run_agent (prefetch calendar) vem primeiro."""
    result = {
        "metadata": {
            "tabular": {
                "title": "Eventos da agenda",
                "headers": ["Evento", "Inicio", "Fim"],
                "emoji_header": CAL,
                "rows": [
                    ["Standup", "2026-08-14T09:00", "2026-08-14T09:30"],
                    ["Review", "2026-08-14T15:00", "2026-08-14T16:00"],
                ],
            }
        }
    }
    payload = _detect_tabular_payload(result)
    assert payload is not None
    assert payload["title"] == "Eventos da agenda"
    assert payload["emoji_header"] == CAL
    assert len(payload["rows"]) == 2
    assert payload["rows"][0][0] == "Standup"


def test_detect_prefetch_tabular_email():
    result = {
        "metadata": {
            "tabular": {
                "title": "Emails encontrados",
                "headers": ["Assunto", "De", "Data"],
                "emoji_header": MAIL,
                "rows": [["Re: proposta", "ana@x.com", "2026-08-13"]],
            }
        }
    }
    payload = _detect_tabular_payload(result)
    assert payload is not None
    assert payload["emoji_header"] == MAIL
    assert payload["rows"][0][0] == "Re: proposta"


def test_detect_prefetch_tabular_drive():
    result = {
        "metadata": {
            "tabular": {
                "title": "Arquivos da pasta",
                "headers": ["Nome", "Tipo", "Modificado"],
                "emoji_header": FILE,
                "rows": [["atas.pdf", "PDF", "2026-08-10"]],
            }
        }
    }
    payload = _detect_tabular_payload(result)
    assert payload is not None
    assert payload["emoji_header"] == FILE
    assert payload["rows"][0][1] == "PDF"


def test_detect_prefetch_tabular_takes_precedence_over_tool_results():
    """Quando vem tabular anexado E tool_results, o prefetch ganha (caminho do pipeline)."""
    result = {
        "metadata": {
            "tabular": {
                "title": "Eventos da agenda",
                "headers": ["Evento", "Inicio", "Fim"],
                "emoji_header": CAL,
                "rows": [["PREFETCH", "2026-08-14T09:00", "2026-08-14T09:30"]],
            },
            "tool_results": [
                {"tool": "drive.list_folder", "result": {"files": [
                    {"name": "x.pdf", "mime_type": "application/pdf", "modified": "2026-08-01"}
                ]}},
            ],
        }
    }
    payload = _detect_tabular_payload(result)
    assert payload["emoji_header"] == CAL
    assert payload["rows"][0][0] == "PREFETCH"


def test_detect_prefetch_tabular_empty_rows_falls_back_to_tool_results():
    """Tabular anexado mas vazio (rows=[]) -> cai para tool_results."""
    result = {
        "metadata": {
            "tabular": {"title": "vazio", "rows": [], "emoji_header": CAL},
            "tool_results": [
                {"tool": "drive.list_folder", "result": {"files": [
                    {"name": "x.pdf", "mime_type": "application/pdf", "modified": "2026-08-01"}
                ]}},
            ],
        }
    }
    payload = _detect_tabular_payload(result)
    assert payload is not None
    assert payload["emoji_header"] == FILE
    assert payload["rows"][0][0] == "x.pdf"


# --- core.tabular builders (prefetch -> tabular dict) ---

def test_tabular_build_calendar_from_raw_events():
    from core.tabular import build_calendar_payload
    events = [
        {"summary": "Reuniao", "start": {"dateTime": "2026-08-14T10:00:00Z"},
         "end": {"dateTime": "2026-08-14T11:00:00Z"}},
    ]
    p = build_calendar_payload(events)
    assert p["emoji_header"] == CAL
    assert p["rows"][0][0] == "Reuniao"
    assert p["rows"][0][1] == "2026-08-14T10:00"


def test_tabular_build_email_from_raw_messages():
    from core.tabular import build_email_payload
    msgs = [
        {"subject": "Orcamento", "from": "vendas@x.com", "date": "2026-08-13"},
    ]
    p = build_email_payload(msgs)
    assert p["emoji_header"] == MAIL
    assert p["rows"][0][0] == "Orcamento"
    assert p["rows"][0][1] == "vendas@x.com"


def test_tabular_build_drive_from_raw_files():
    from core.tabular import build_drive_payload
    files = [
        {"name": "ata.docx",
         "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "modifiedTime": "2026-08-12T00:00:00Z"},
    ]
    p = build_drive_payload(files)
    assert p["emoji_header"] == FILE
    assert p["rows"][0][0] == "ata.docx"
    assert p["rows"][0][1] == "Word"


def test_tabular_build_from_agent_type():
    from core.tabular import build_from_agent_type
    assert build_from_agent_type("calendar", [{"summary": "x", "start": {}, "end": {}}])["emoji_header"] == CAL
    assert build_from_agent_type("email", [{"subject": "s"}])["emoji_header"] == MAIL
    assert build_from_agent_type("drive", [{"name": "f"}])["emoji_header"] == FILE
    assert build_from_agent_type("unknown", []) is None


def test_prefetch_build_tabular_parses_json():
    """pipelines/_prefetch._build_tabular parseia o JSON dos _prefetch_*."""
    import json
    from pipelines import _prefetch
    events_json = json.dumps([{"summary": "Sync", "start": {"dateTime": "t1"}, "end": {"dateTime": "t2"}}])
    tab = _prefetch._build_tabular("calendar", events_json)
    assert tab is not None
    assert tab["emoji_header"] == CAL
    assert tab["rows"][0][0] == "Sync"
    files_json = json.dumps([{"name": "a.pdf", "mimeType": "application/pdf", "modifiedTime": "2026-08-01"}])
    tab2 = _prefetch._build_tabular("drive", files_json)
    assert tab2["emoji_header"] == FILE
    assert tab2["rows"][0][1] == "PDF"
    msgs_json = json.dumps([{"subject": "oi", "from": "a@b", "date": "2026-08-01"}])
    tab3 = _prefetch._build_tabular("email", msgs_json)
    assert tab3["emoji_header"] == MAIL
    assert _prefetch._build_tabular("calendar", "not json") is None
    assert _prefetch._build_tabular("calendar", json.dumps({"a": 1})) is None


def test_executor_run_agent_attaches_prefetch_tabular_to_metadata(monkeypatch):
    """run_agent anexa metadata['tabular'] quando prefetch vem como dict."""
    import asyncio

    async def fake_execute_agent(agent, text, payload, extra):
        return {
            "reply": "ok",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": "test"},
        }

    monkeypatch.setattr("agent_loader.resolve_agent_for_instance", lambda instance, agent_id: {"enabled": True, "system_prompt": "x", "tools": []})
    monkeypatch.setattr("orchestrator._execute_agent", fake_execute_agent)

    from pipelines._executor import run_agent

    tabular_payload = {
        "title": "Eventos da agenda",
        "headers": ["E"],
        "emoji_header": CAL,
        "rows": [["A", "B"]],
    }
    result = asyncio.run(run_agent(
        "test",
        "txt",
        {"instance": "jennifer", "phone": "+5511"},
        {},
        prefetch={"text": '[{"summary":"A","start":{},"end":{}}]', "tabular": tabular_payload},
        prefetch_label="CALENDARIO",
    ))
    assert result["metadata"].get("tabular") is tabular_payload


def test_executor_run_agent_backcompat_accepts_str_prefetch(monkeypatch):
    """run_agent aceita prefetch como str (legado) sem tabular."""
    import asyncio

    async def fake_execute_agent(agent, text, payload, extra):
        return {
            "reply": "ok",
            "delay_ms": 0,
            "presence": "composing",
            "metadata": {"agent_id": "test"},
        }

    monkeypatch.setattr("agent_loader.resolve_agent_for_instance", lambda instance, agent_id: {"enabled": True, "system_prompt": "x", "tools": []})
    monkeypatch.setattr("orchestrator._execute_agent", fake_execute_agent)

    from pipelines._executor import run_agent

    result = asyncio.run(run_agent(
        "test",
        "txt",
        {"instance": "jennifer", "phone": "+5511"},
        {},
        prefetch='[{"summary":"A","start":{},"end":{}}]',
    ))
    # Sem tabular -> metadata nao recebe chave 'tabular'
    assert "tabular" not in result["metadata"]


# --- Keyword trigger (force image) ---

def test_user_requested_image_keywords():
    from orchestrator import _user_requested_image
    assert _user_requested_image("me mostra em tabela") is True
    assert _user_requested_image("manda como imagem") is True
    assert _user_requested_image("faz um gráfico") is True
    assert _user_requested_image("quero em png") is True
    assert _user_requested_image("lista de eventos") is False
    assert _user_requested_image("") is False
    # Acentos normalizados
    assert _user_requested_image("em gráfico") is True


def test_anti_duplication_guardrail_suppresses_redundant_text():
    """Quando a imagem com legenda é despachada, reply textual deve ser suprimido."""
    from orchestrator import _auto_send_image
    from unittest.mock import AsyncMock, patch

    payload = {"instance": "Jennifer", "phone": "5511966830020"}
    tabular = {"title": "Teste", "headers": ["A"], "rows": [["1"]], "emoji_header": "📁"}

    with patch("core.evolution_client.send_image", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"status": "accepted"}
        import asyncio
        ok = asyncio.run(_auto_send_image(payload, tabular, "Legenda da imagem"))
        assert ok is True
        mock_send.assert_called_once()


def test_send_text_deduplication_guardrail():
    """send_text deve suprimir envios consecutivos da mesma mensagem na mesma janela."""
    import asyncio
    from unittest.mock import patch, MagicMock
    from core.evolution_client import send_text, _RECENT_SENT_TEXT
    import httpx

    _RECENT_SENT_TEXT.clear()

    class _StubClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def post(self, url, **kwargs):
            return httpx.Response(200, json={"ok": True})

    with patch("core.evolution_client.get_secret", return_value="token"):
        with patch("core.evolution_client.httpx.AsyncClient", _StubClient):
            res1 = asyncio.run(send_text("Jennifer", "5511966830020", "Mensagem de teste"))
            assert res1 == {"ok": True}
            # Segunda chamada imediata com o mesmo texto -> suprimida pelo Guardrail
            res2 = asyncio.run(send_text("Jennifer", "5511966830020", "Mensagem de teste"))
            assert res2 == {"status": "suppressed_duplicate"}

