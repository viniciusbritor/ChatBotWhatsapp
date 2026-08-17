"""Tests para core/approval_store.py (FASE 1)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# Helper classes para simular Firestore de forma deterministica
class FakeSnapshot:
    """Snapshot simulado do Firestore."""
    def __init__(self, data: dict):
        self._data = data
        self.exists = bool(data)

    def to_dict(self):
        return self._data


class FakeDocumentRef:
    """DocumentRef simulado."""
    def __init__(self, data: dict):
        self._data = data
        self.update_calls = []

    def get(self, *args, **kwargs):
        return FakeSnapshot(self._data)

    def update(self, ref, updates):
        self.update_calls.append(updates)
        # Em runtime real, o Firestore faz commit atomico agora.
        self._data.update(updates)


def _setup_db_for_apply(mock_db, doc_data: dict):
    """Configura mock_db para retornar FakeDocumentRef com doc_data."""
    mock_doc_ref = FakeDocumentRef(doc_data)
    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc_ref
    mock_db.collection.return_value = mock_collection
    return mock_doc_ref


# Testes para get_pending_approval (mais simples, nao precisa de FakeDocumentRef)
def _make_doc_mock(run_id: str, phone: str, name: str, intent: str,
                  status: str = "pending", created_at: str = None) -> MagicMock:
    """Helper para criar mock de doc Firestore (testes que nao usam apply)."""
    if created_at is None:
        created_at = datetime.now(timezone.utc).astimezone().isoformat()
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {
        "run_id": run_id,
        "phone": phone,
        "name": name,
        "intent": intent,
        "message": "quero meu perfil",
        "status": status,
        "created_at": created_at,
    }
    return doc


class TestCreatePendingApproval:
    def test_create_returns_run_id(self):
        from core import approval_store
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch.object(approval_store, "_db", return_value=mock_db):
            run_id = approval_store.create_pending_approval(
                phone="5511999999999",
                name="Pedro Costa",
                intent="linkedin.read",
                message="quero meu perfil",
            )

        assert run_id is not None
        assert len(run_id) == 12  # uuid[:12]
        mock_doc_ref.set.assert_called_once()

    def test_create_saves_correct_payload(self):
        from core import approval_store
        mock_db = MagicMock()
        mock_doc_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_doc_ref

        with patch.object(approval_store, "_db", return_value=mock_db):
            approval_store.create_pending_approval(
                phone="5511999999999",
                name="Maria Silva",
                intent="email.read",
                message="quero meu email",
            )

        payload = mock_doc_ref.set.call_args[0][0]
        assert payload["phone"] == "5511999999999"
        assert payload["name"] == "Maria Silva"
        assert payload["intent"] == "email.read"
        assert payload["message"] == "quero meu email"
        assert payload["status"] == "pending"
        assert "created_at" in payload


class TestGetPendingApproval:
    def test_get_returns_approval_when_exists(self):
        from core import approval_store
        mock_db = MagicMock()
        mock_doc = _make_doc_mock("abc-1234", "5511999999999", "Pedro", "email.read")
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch.object(approval_store, "_db", return_value=mock_db):
            req = approval_store.get_pending_approval("abc-1234")

        assert req is not None
        assert req.run_id == "abc-1234"
        assert req.phone == "5511999999999"
        assert req.name == "Pedro"
        assert req.intent == "email.read"
        assert req.status == "pending"

    def test_get_returns_none_when_not_exists(self):
        from core import approval_store
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch.object(approval_store, "_db", return_value=mock_db):
            req = approval_store.get_pending_approval("inexistente")

        assert req is None


class TestGetPendingForAdmin:
    def test_returns_oldest_pending(self):
        from core import approval_store
        mock_db = MagicMock()
        mock_doc = _make_doc_mock("abc-1234", "5511999999999", "Pedro", "email.read")
        mock_db.collection.return_value.where.return_value.order_by.return_value.limit.return_value.stream.return_value = iter([mock_doc])

        with patch.object(approval_store, "_db", return_value=mock_db):
            req = approval_store.get_pending_for_admin()

        assert req is not None
        assert req.run_id == "abc-1234"

    def test_returns_none_when_no_pending(self):
        from core import approval_store
        mock_db = MagicMock()
        mock_db.collection.return_value.where.return_value.order_by.return_value.limit.return_value.stream.return_value = iter([])

        with patch.object(approval_store, "_db", return_value=mock_db):
            req = approval_store.get_pending_for_admin()

        assert req is None


class TestApplyDecision:
    def test_apply_returns_true_on_first_call(self):
        """Aplica decisao com sucesso (status pending -> approved)."""
        from core import approval_store
        mock_db = MagicMock()
        mock_doc_ref = _setup_db_for_apply(mock_db, {
            "run_id": "abc-1234",
            "phone": "5511999999999",
            "name": "Pedro",
            "intent": "email.read",
            "message": "quero meu email",
            "status": "pending",
            "created_at": "2026-08-17T10:00:00-03:00",
        })

        with patch.object(approval_store, "_db", return_value=mock_db):
            mock_tx = MagicMock()
            mock_db.transaction.return_value = mock_tx

            applied = approval_store.apply_decision(
                run_id="abc-1234",
                decision="approved",
                admin_phone="5511966830020",
            )

        assert applied is True
        # Em runtime real, Firestore transaction.update eh chamado.
        # Em mock, transaction eh um MagicMock, entao checamos via mock_tx.
        assert mock_tx.update.called
        update_kwargs = mock_tx.update.call_args[0]
        # Segundo argumento eh o dict de updates
        update_dict = update_kwargs[1] if len(update_kwargs) > 1 else update_kwargs[0]
        assert update_dict["status"] == "approved"
        assert update_dict["applied_by"] == "5511966830020"
        assert "applied_at" in update_dict

    def test_apply_returns_false_on_double_apply(self):
        """Idempotencia: 2a chamada nao aplica se ja foi aplicada."""
        from core import approval_store
        mock_db = MagicMock()
        mock_doc_ref = _setup_db_for_apply(mock_db, {
            "run_id": "abc-1234",
            "phone": "5511999999999",
            "name": "Pedro",
            "intent": "email.read",
            "message": "x",
            "status": "approved",  # JA FOI APLICADO
            "created_at": "2026-08-17T10:00:00-03:00",
        })

        with patch.object(approval_store, "_db", return_value=mock_db):
            mock_tx = MagicMock()
            mock_db.transaction.return_value = mock_tx

            applied = approval_store.apply_decision(
                run_id="abc-1234",
                decision="rejected",  # admin tenta rejeitar DEPOIS de aprovado
                admin_phone="5511966830020",
            )

        assert applied is False
        assert not mock_tx.update.called

    def test_apply_returns_false_when_run_id_not_found(self):
        from core import approval_store
        mock_db = MagicMock()
        # Empty data (doc nao existe)
        mock_doc_ref = FakeDocumentRef({})

        mock_collection = MagicMock()
        mock_collection.document.return_value = mock_doc_ref
        mock_db.collection.return_value = mock_collection

        with patch.object(approval_store, "_db", return_value=mock_db):
            mock_tx = MagicMock()
            mock_db.transaction.return_value = mock_tx

            applied = approval_store.apply_decision(
                run_id="inexistente",
                decision="approved",
                admin_phone="5511966830020",
            )

        assert applied is False
        assert not mock_tx.update.called


class TestListPending:
    def test_list_returns_only_pending(self):
        from core import approval_store
        mock_db = MagicMock()
        mock_doc1 = _make_doc_mock("doc-1", "5511111111111", "User1", "email.read")
        mock_doc2 = _make_doc_mock("doc-2", "5511222222222", "User2", "linkedin.read")
        mock_db.collection.return_value.where.return_value.order_by.return_value.limit.return_value.stream.return_value = iter([mock_doc1, mock_doc2])

        with patch.object(approval_store, "_db", return_value=mock_db):
            pending = approval_store.list_pending()

        assert len(pending) == 2
        assert pending[0].run_id == "doc-1"
        assert pending[1].run_id == "doc-2"

    def test_get_pending_count(self):
        from core import approval_store
        mock_db = MagicMock()
        mock_doc1 = _make_doc_mock("doc-1", "5511111111111", "User1", "email.read")
        mock_doc2 = _make_doc_mock("doc-2", "5511222222222", "User2", "linkedin.read")
        mock_db.collection.return_value.where.return_value.stream.return_value = iter([mock_doc1, mock_doc2])

        with patch.object(approval_store, "_db", return_value=mock_db):
            count = approval_store.get_pending_count()

        assert count == 2


class TestApprovalRequestDataclass:
    def test_approval_request_from_dict(self):
        from core.approval_store import ApprovalRequest
        data = {
            "run_id": "abc-1234",
            "phone": "5511999999999",
            "name": "Pedro",
            "intent": "email.read",
            "message": "quero meu email",
            "status": "pending",
            "created_at": "2026-08-17T10:00:00-03:00",
        }
        req = ApprovalRequest(**data)
        assert req.run_id == "abc-1234"
        assert req.applied_at is None
        assert req.applied_by is None

    def test_approval_request_with_applied_fields(self):
        from core.approval_store import ApprovalRequest
        data = {
            "run_id": "abc-1234",
            "phone": "5511999999999",
            "name": "Pedro",
            "intent": "email.read",
            "message": "quero meu email",
            "status": "approved",
            "created_at": "2026-08-17T10:00:00-03:00",
            "applied_at": "2026-08-17T10:01:00-03:00",
            "applied_by": "5511966830020",
        }
        req = ApprovalRequest(**data)
        assert req.applied_at is not None
        assert req.applied_by == "5511966830020"