"""Testes do FIX Bug #1A (15/08/2026): acks consolidados no _handle_attachment.

Antes do fix, quando o usuario pedia para memorizar/salvar um arquivo,
o handler disparava 2 ``_send_ack`` separados ("ok. pode deixar" e
"estou memorizando o conteudo"), mais o reply final. Resultado: o
usuario recebia 3+ mensagens no WhatsApp para UMA acao. Estes testes
garantem que:
- Apenas 1 ack e disparado em _send_ack (mensagem consolidada).
- O reply final do _handle_attachment continua sendo retornado.
- O log estruturado ``attachment_routing`` e emitido com a decisao.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _envelope():
    return {
        "instance": "Jennifer",
        "phone": "5511966830020",
        "remote_jid": "120363@g.us",
        "message_id": "test-bug-1a-001",
        "sender_name": "Vinicius",
        "text": "guarde no gdrive na pasta curriculo",
        "extra": {
            "is_group": True,
            "remote_jid": "120363@g.us",
            "has_document": True,
            "doc_mimetype": "application/pdf",
            "doc_file_name": "Curriculo.pdf",
            "doc_url": "https://mmg.whatsapp.net/v/t62.pdf",
        },
    }


@pytest.mark.asyncio
async def test_handle_attachment_sends_single_ack_when_saving():
    """Para 'salvar' (is_file=True), apenas 1 _send_ack deve ser chamado."""
    from orchestrator import _handle_attachment

    sent_texts: list[str] = []

    async def fake_send_text(**kwargs):
        sent_texts.append(kwargs.get("text", ""))

    extracted = {
        "text": "conteudo do curriculo",
        "source_name": "Curriculo.pdf",
        "mimetype": "application/pdf",
        "raw_size": 12345,
    }
    persist_result = {
        "status": "drive_individual",
        "chunks_indexed": 0,
        "index_result": {"chunks_indexed": 0},
    }
    intent = {
        "is_attachment": True,
        "is_attachment_save": False,
        "is_attachment_file": True,
    }
    with patch("core.evolution_client.send_text", side_effect=fake_send_text), patch(
        "orchestrator._extract_text_from_attachment", new_callable=AsyncMock, return_value=extracted
    ), patch(
        "orchestrator._persist_attachment", new_callable=AsyncMock, return_value=persist_result
    ):
        result = await _handle_attachment(_envelope(), intent, "Vinicius")

    ack_msgs = [t for t in sent_texts if "ok" in t.lower() or "pode deixar" in t.lower() or "memorizando" in t.lower() or "salvando" in t.lower()]
    assert len(ack_msgs) == 1, f"Esperado 1 ack, recebido {len(ack_msgs)}: {ack_msgs}"
    assert result["reply"].startswith("Feito")
    assert "Salvei" in result["reply"] or "💾" in result["reply"]


@pytest.mark.asyncio
async def test_handle_attachment_sends_single_ack_when_memorizing():
    """Para 'memorizar' (is_save=True), apenas 1 _send_ack deve ser chamado."""
    from orchestrator import _handle_attachment

    sent_texts: list[str] = []

    async def fake_send_text(**kwargs):
        sent_texts.append(kwargs.get("text", ""))

    extracted = {
        "text": "conteudo do doc",
        "source_name": "Curriculo.pdf",
        "mimetype": "application/pdf",
        "raw_size": 12345,
    }
    persist_result = {
        "status": "rag_individual",
        "chunks_indexed": 8,
        "index_result": {"chunks_indexed": 8},
    }
    intent = {
        "is_attachment": True,
        "is_attachment_save": True,
        "is_attachment_file": False,
    }
    with patch("core.evolution_client.send_text", side_effect=fake_send_text), patch(
        "orchestrator._extract_text_from_attachment", new_callable=AsyncMock, return_value=extracted
    ), patch(
        "orchestrator._persist_attachment", new_callable=AsyncMock, return_value=persist_result
    ):
        result = await _handle_attachment(_envelope(), intent, "Vinicius")

    ack_msgs = [t for t in sent_texts if "ok" in t.lower() or "pode deixar" in t.lower() or "memorizando" in t.lower()]
    assert len(ack_msgs) == 1, f"Esperado 1 ack, recebido {len(ack_msgs)}: {ack_msgs}"
    assert "Memorei" in result["reply"]


@pytest.mark.asyncio
async def test_attachment_routing_log_emitted_with_decision():
    """O log estruturado ``attachment_routing`` deve indicar rag/drive."""
    from orchestrator import _handle_attachment

    async def fake_send_text(**kwargs):
        pass

    extracted = {
        "text": "x",
        "source_name": "Curriculo.pdf",
        "mimetype": "application/pdf",
        "raw_size": 12345,
    }
    persist_result = {
        "status": "rag_individual",
        "chunks_indexed": 4,
        "index_result": {"chunks_indexed": 4},
    }
    intent = {
        "is_attachment": True,
        "is_attachment_save": True,
        "is_attachment_file": False,
    }
    with patch("core.evolution_client.send_text", side_effect=fake_send_text), patch(
        "orchestrator._extract_text_from_attachment", new_callable=AsyncMock, return_value=extracted
    ), patch(
        "orchestrator._persist_attachment", new_callable=AsyncMock, return_value=persist_result
    ), patch("orchestrator.logger") as mock_logger:
        await _handle_attachment(_envelope(), intent, "Vinicius")

    routing_logs = [
        call.args[0]
        for call in mock_logger.info.call_args_list
        if call.args and "attachment_routing" in str(call.args[0])
    ]
    assert routing_logs, f"Nenhum log attachment_routing emitido. Logs: {[c.args for c in mock_logger.info.call_args_list]}"
    # O log usa %s format. Verificar os args do call que tem 'attachment_routing'
    matching = [
        call
        for call in mock_logger.info.call_args_list
        if call.args and "attachment_routing" in str(call.args[0])
    ]
    assert matching, "attachment_routing nao encontrado"
    # args = ("template", phone, decision, save_to_rag, source)
    args = matching[0].args
    assert "rag" in str(args[2]), f"Esperado decision=rag em args[2], recebido {args}"
    assert args[3] is True, f"Esperado save_to_rag=True, recebido {args[3]}"


@pytest.mark.asyncio
async def test_attachment_ambiguous_returns_ask_for_mode():
    """Quando intent e ambiguo, o handler deve perguntar memorizar/salvar (sem _send_ack de save)."""
    from orchestrator import _handle_attachment

    sent_texts: list[str] = []

    async def fake_send_text(**kwargs):
        sent_texts.append(kwargs.get("text", ""))

    envelope = _envelope()
    envelope["text"] = ""  # sem keyword para cair no ambíguo
    intent = {
        "is_attachment": True,
        "is_attachment_save": False,
        "is_attachment_file": False,
    }
    with patch("core.evolution_client.send_text", side_effect=fake_send_text), patch(
        "core.pending_actions.set_pending_action", new_callable=AsyncMock
    ):
        result = await _handle_attachment(envelope, intent, "Vinicius")

    assert "Aguardando" in result["reply"] or "memorizar" in result["reply"].lower()
    ack_msgs = [t for t in sent_texts if "memorizar" in t.lower() or "salvar" in t.lower()]
    assert len(ack_msgs) <= 1, f"Ambíguo nao deve ter mais de 1 ack: {ack_msgs}"
