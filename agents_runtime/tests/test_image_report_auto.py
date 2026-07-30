"""Tests for tabular payload detection + auto-image render (F4d.9).

When the agent's metadata contains a tool_result for a tabular source
(drive.list_folder, gmail.search_messages, calendar.list_events),
the orchestrator should auto-detect it and produce a PNG payload.
"""
import base64

from orchestrator import _detect_tabular_payload


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
    assert payload["emoji_header"] == "📁"
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
    assert payload["emoji_header"] == "📧"


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
    assert payload["emoji_header"] == "📅"


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
        emoji_header="📁",
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
    assert payload["emoji_header"] == "\U0001F4DA"
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
