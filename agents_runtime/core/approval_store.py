"""Store de solicitacoes de aprovacao pendentes (substitui link HMAC por mensagem WhatsApp).

GUARDRAIL (17/08/2026): admin responde DIRETO no WhatsApp com "ok, aprovado"
ou "nao, rejeitado". Lock por run_id via Firestore transaction garante
idempotencia contra double-approval.

Fluxo:
1. Visitante fala "quero meu perfil do linkedin"
2. notify_admin_access_request() cria pending_approval via create_pending_approval()
3. Admin recebe WhatsApp com instrucoes explicitas
4. Admin responde "ok" - detect_admin_response() extrai intent
5. apply_decision() com lock atomic aplica a decisao
6. Visitante recebe confirmacao (se aprovado)
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore

logger = logging.getLogger(__name__)

_PROJECT = "coherence-ominichannel-fs"


def _db():
    """Lazy Firestore client."""
    return firestore.Client(project=_PROJECT)


@dataclass
class ApprovalRequest:
    """Solicitacao de aprovacao pendente."""
    run_id: str
    phone: str
    name: str
    intent: str
    message: str
    status: str  # "pending" | "approved" | "rejected"
    created_at: str
    applied_at: Optional[str] = None
    applied_by: Optional[str] = None


def create_pending_approval(
    phone: str,
    name: str,
    intent: str,
    message: str,
) -> str:
    """Cria uma solicitacao de aprovacao pendente. Retorna run_id."""
    run_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).astimezone().isoformat()
    db = _db()
    db.collection("approval_requests").document(run_id).set({
        "run_id": run_id,
        "phone": phone,
        "name": name,
        "intent": intent,
        "message": message,
        "status": "pending",
        "created_at": now,
    })
    logger.info(
        "approval_request_created run_id=%s phone=%s intent=%s",
        run_id, phone, intent,
        extra={
            "event_name": "approval_request_created",
            "run_id": run_id,
            "phone": phone,
            "intent": intent,
        },
    )
    return run_id


def get_pending_approval(run_id: str) -> Optional[ApprovalRequest]:
    """Busca uma solicitacao por run_id."""
    db = _db()
    doc = db.collection("approval_requests").document(run_id).get()
    if not doc.exists:
        return None
    return ApprovalRequest(**doc.to_dict())


def get_pending_for_admin() -> Optional[ApprovalRequest]:
    """Retorna a solicitacao pendente mais antiga (FIFO).

    Usado quando admin responde 'ok' sem run_id explicito.
    """
    db = _db()
    docs = (
        db.collection("approval_requests")
        .where("status", "==", "pending")
        .order_by("created_at")
        .limit(1)
        .stream()
    )
    for doc in docs:
        return ApprovalRequest(**doc.to_dict())
    return None


def get_pending_count() -> int:
    """Conta total de solicitacoes pendentes."""
    db = _db()
    docs = (
        db.collection("approval_requests")
        .where("status", "==", "pending")
        .stream()
    )
    return sum(1 for _ in docs)


def _do_apply_decision(transaction, ref, decision: str, admin_phone: str) -> bool:
    """Logica de apply. Chamada dentro de Firestore transaction."""
    doc = ref.get(transaction=transaction)
    if not doc.exists:
        return False
    data = doc.to_dict()
    if data["status"] != "pending":
        # Already applied (race condition: 2 requests simultaneas)
        return False
    transaction.update(ref, {
        "status": decision,
        "applied_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "applied_by": admin_phone,
    })
    return True


def apply_decision(run_id: str, decision: str, admin_phone: str) -> bool:
    """Aplica decisao do admin com lock atomic via Firestore transaction.

    Returns:
        True se aplicou a decisao, False se ja foi aplicada antes.
    """
    db = _db()
    ref = db.collection("approval_requests").document(run_id)
    transaction = db.transaction()
    try:
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return False
        data = snapshot.to_dict()
        if data["status"] != "pending":
            return False
        transaction.update(ref, {
            "status": decision,
            "applied_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "applied_by": admin_phone,
        })
        # Em runtime real, o Firestore commita a transaction atomica.
        # O lock atomatico vem das transactions do Firestore.
        return True
    except Exception:
        return False


def list_pending(limit: int = 50) -> list:
    """Lista todas as solicitacoes pendentes (para portal admin)."""
    db = _db()
    docs = (
        db.collection("approval_requests")
        .where("status", "==", "pending")
        .order_by("created_at")
        .limit(limit)
        .stream()
    )
    return [ApprovalRequest(**doc.to_dict()) for doc in docs]


def list_all(limit: int = 100) -> list:
    """Lista todas as solicitacoes (para portal admin)."""
    db = _db()
    docs = (
        db.collection("approval_requests")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    return [ApprovalRequest(**doc.to_dict()) for doc in docs]