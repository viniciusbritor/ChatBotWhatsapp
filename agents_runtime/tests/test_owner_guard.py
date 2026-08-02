"""Tests para owner bypass em core/owner_guard.py (01/08/2026).

Bug original: TASK B enforcement (commit ae16321, 30/07/2026) bloqueou o
owner da instance porque folder_permissions doc estava vazio no Firestore.
Owner tinha que adivinhar que precisava criar grant wildcard via admin
endpoint. Tools NAO podiam falhar para o owner.

Fix: ``_check_folder_permission`` agora retorna ``None`` (allow) sem
consultar Firestore quando o phone resolve para owner da instance via
``resolve_owner``. TASK B continua valendo para non-owners.

Estes testes protegem contra regressao onde owner bypass e quebrado ou
removido.

Nota: conftest.py seta RAG_FOLDER_PERMISSIONS_ENFORCE=false por padrao
(para nao quebrar testes legados). Este arquivo re-liga via
``_enforce_enabled`` fixture (autouse).
"""
from unittest.mock import patch, MagicMock

import pytest

from core.owner import OwnerResolution


OWNER_DIGITS = "5511966830020"
NON_OWNER_DIGITS = "5511999999999"
INSTANCE = "Jennifer"


@pytest.fixture(autouse=True)
def _enforce_enabled(monkeypatch):
    """Re-liga o enforcement de folder_permissions. Sem isso, conftest.py
    desliga por padrao e o bypass nao roda (early return na linha 89)."""
    monkeypatch.setenv("RAG_FOLDER_PERMISSIONS_ENFORCE", "true")
    yield


def _make_owner_resolution(phone=OWNER_DIGITS):
    """Helper para construir OwnerResolution mockado."""
    return OwnerResolution(
        owner_phone=phone,
        owner_uid=phone,
        account_id="acc-test",
        instance=INSTANCE,
    )


class TestOwnerBypassTASKB:
    """Owner da instance recebe allow em qualquer capability sem consultar
    folder_permissions."""

    def test_owner_bypass_returns_none_when_folder_permissions_empty(self):
        """Cenario principal do bug: owner, folder_permissions vazio,
        capability drive.list -> bypass ativo, retorna None (allow)."""
        from core.owner_guard import _check_folder_permission

        with patch(
            "core.owner_guard.resolve_owner",
            return_value=_make_owner_resolution(),
        ) as mock_resolve, \
             patch(
                 "core.folder_permissions.get_user_allowed_tools",
                 return_value={"drive": [], "gmail": [], "calendar": []},
             ) as mock_get:
            denial = _check_folder_permission(
                phone=OWNER_DIGITS,
                capability="drive.list",
                kwargs={"instance": INSTANCE, "phone": OWNER_DIGITS},
            )

        assert denial is None, (
            f"Owner bypass falhou. denial={denial}. "
            f"resolve_owner called={mock_resolve.called}, "
            f"get_user_allowed_tools called={mock_get.called}"
        )
        # CRITICO: get_user_allowed_tools NAO deve ter sido chamado para owner.
        # Bypass retorna antes de consultar Firestore.
        assert not mock_get.called, (
            "owner bypass NAO deveria chamar get_user_allowed_tools (vai Firestore). "
            f"Calls: {mock_get.call_args_list}"
        )

    @pytest.mark.parametrize("capability", [
        "drive.list", "drive.search", "drive.upload", "drive.read_file",
        "drive.deep_search", "drive.find_omnichannel_atas", "drive.create_folder",
        "gmail.search", "gmail.thread", "gmail.send",
        "calendar.list", "calendar.create", "calendar.update",
    ])
    def test_owner_bypass_active_for_all_google_capabilities(self, capability):
        """Owner bypass deve funcionar para TODAS as capabilities do CAPABILITY_TO_TOOL."""
        from core.owner_guard import _check_folder_permission

        with patch(
            "core.owner_guard.resolve_owner",
            return_value=_make_owner_resolution(),
        ), \
             patch(
                 "core.folder_permissions.get_user_allowed_tools",
                 return_value={"drive": [], "gmail": [], "calendar": []},
             ) as mock_get:
            denial = _check_folder_permission(
                phone=OWNER_DIGITS,
                capability=capability,
                kwargs={"instance": INSTANCE, "phone": OWNER_DIGITS},
            )

        assert denial is None, (
            f"owner bypass falhou para {capability!r}: {denial}"
        )
        assert not mock_get.called

    def test_owner_bypass_with_existing_whitelist_still_allows(self):
        """Mesmo se folder_permissions TEM whitelist, owner recebe allow
        (bypass ignora whitelist completamente)."""
        from core.owner_guard import _check_folder_permission

        with patch(
            "core.owner_guard.resolve_owner",
            return_value=_make_owner_resolution(),
        ), \
             patch(
                 "core.folder_permissions.get_user_allowed_tools",
                 return_value={"drive": ["specific-folder-id"], "gmail": [], "calendar": []},
             ) as mock_get:
            denial = _check_folder_permission(
                phone=OWNER_DIGITS,
                capability="drive.list",
                kwargs={
                    "instance": INSTANCE,
                    "phone": OWNER_DIGITS,
                    "folder_id": "different-folder-not-in-whitelist",
                },
            )

        assert denial is None, (
            f"owner bypass deveria ignorar whitelist restritiva. denial={denial}"
        )
        assert not mock_get.called

    def test_non_owner_without_whitelist_still_denied(self):
        """Non-owner sem folder_permissions NAO recebe bypass — TASK B
        lock-down continua valendo para multi-user futuro."""
        from core.owner_guard import _check_folder_permission

        with patch(
            "core.owner_guard.resolve_owner",
            return_value=_make_owner_resolution(phone=OWNER_DIGITS),
        ), \
             patch(
                 "core.folder_permissions.get_user_allowed_tools",
                 return_value={"drive": [], "gmail": [], "calendar": []},
             ) as mock_get:
            denial = _check_folder_permission(
                phone=NON_OWNER_DIGITS,
                capability="drive.list",
                kwargs={"instance": INSTANCE, "phone": NON_OWNER_DIGITS},
            )

        assert denial is not None, (
            "Non-owner sem whitelist deveria ser bloqueado (TASK B lock-down)"
        )
        assert denial["error"] == "folder_permission_required"
        # Non-owner: get_user_allowed_tools FOI chamado (TASK B aplica)
        assert mock_get.called

    def test_non_owner_with_matching_whitelist_passes(self):
        """Non-owner com whitelist matching o pattern recebe allow."""
        from core.owner_guard import _check_folder_permission

        with patch(
            "core.owner_guard.resolve_owner",
            return_value=_make_owner_resolution(phone=OWNER_DIGITS),
        ), \
             patch(
                 "core.folder_permissions.get_user_allowed_tools",
                 return_value={"drive": ["allowed-folder"], "gmail": [], "calendar": []},
             ):
            denial = _check_folder_permission(
                phone=NON_OWNER_DIGITS,
                capability="drive.list",
                kwargs={
                    "instance": INSTANCE,
                    "phone": NON_OWNER_DIGITS,
                    "folder_id": "allowed-folder",
                },
            )

        assert denial is None

    def test_owner_bypass_with_normalized_phone_variants(self):
        """Phone do owner pode vir com prefixo 55, +, ou sem prefixo.
        Bypass deve reconhecer via normalize (regex non-digits)."""
        from core.owner_guard import _check_folder_permission

        variants = [
            "+5511966830020",
            "5511966830020",
            "11966830020",  # sem prefixo 55 (tambem eh candidate)
            "+55 (11) 96683-0020",  # com formatacao
        ]

        for phone_variant in variants:
            with patch(
                "core.owner_guard.resolve_owner",
                return_value=_make_owner_resolution(),
            ), \
                 patch(
                     "core.folder_permissions.get_user_allowed_tools",
                     return_value={"drive": [], "gmail": [], "calendar": []},
                 ) as mock_get:
                denial = _check_folder_permission(
                    phone=phone_variant,
                    capability="drive.list",
                    kwargs={"instance": INSTANCE, "phone": phone_variant},
                )
            assert denial is None, (
                f"owner bypass falhou para variante {phone_variant!r}: {denial}"
            )
            assert not mock_get.called, (
                f"owner bypass chamou get_user_allowed_tools para variante {phone_variant!r}"
            )


class TestOwnerBypassDisabledByEnvVar:
    """Quando RAG_FOLDER_PERMISSIONS_ENFORCE=false, bypass NAO roda
    (regra geral desligada)."""

    def test_enforce_disabled_skips_owner_bypass(self):
        """Com enforcement desligado, bypass NAO consulta resolve_owner
        (early return None na linha 89-90)."""
        from core.owner_guard import _check_folder_permission

        with patch.dict(os.environ, {"RAG_FOLDER_PERMISSIONS_ENFORCE": "false"}), \
             patch(
                 "core.owner_guard.resolve_owner",
             ) as mock_resolve, \
             patch(
                 "core.folder_permissions.get_user_allowed_tools",
                 return_value={"drive": [], "gmail": [], "calendar": []},
             ) as mock_get:
            denial = _check_folder_permission(
                phone=OWNER_DIGITS,
                capability="drive.list",
                kwargs={"instance": INSTANCE, "phone": OWNER_DIGITS},
            )

        assert denial is None
        assert not mock_resolve.called, (
            "Com RAG_FOLDER_PERMISSIONS_ENFORCE=false, bypass NAO deveria consultar resolve_owner"
        )
        assert not mock_get.called


class TestOwnerBypassFailOpen:
    """Se resolve_owner falha (Firestore down, exception), bypass NAO
    bloqueia — fail-open para check normal."""

    def test_resolve_owner_exception_proceeds_to_normal_check(self):
        """Exception em resolve_owner -> segue com TASK B check normal.
        Se folder_permissions tiver whitelist, passa. Se nao, bloqueia."""
        from core.owner_guard import _check_folder_permission

        with patch(
            "core.owner_guard.resolve_owner",
            side_effect=RuntimeError("firestore down"),
        ), \
             patch(
                 "core.folder_permissions.get_user_allowed_tools",
                 return_value={"drive": [], "gmail": [], "calendar": []},
             ):
            denial = _check_folder_permission(
                phone=OWNER_DIGITS,
                capability="drive.list",
                kwargs={"instance": INSTANCE, "phone": OWNER_DIGITS},
            )

        # Fail-open: resolve_owner falhou -> aplica TASK B normalmente
        # Owner (sem whitelist) sera bloqueado. Isso e aceitavel: melhor
        # bloquear que dar acesso indevido em caso de erro.
        assert denial is not None
        assert denial["error"] == "folder_permission_required"


class TestOwnerBypassWithoutInstance:
    """Quando kwargs nao tem instance, bypass tenta via fallback_phone."""

    def test_no_instance_kwargs_proceeds_to_normal_check(self):
        """Sem instance em kwargs, resolve_owner retornara None (nao
        consegue determinar owner). Bypass NAO ativa. TASK B aplica."""
        from core.owner_guard import _check_folder_permission

        with patch(
            "core.owner_guard.resolve_owner",
            return_value=None,
        ), \
             patch(
                 "core.folder_permissions.get_user_allowed_tools",
                 return_value={"drive": [], "gmail": [], "calendar": []},
             ):
            denial = _check_folder_permission(
                phone=OWNER_DIGITS,
                capability="drive.list",
                kwargs={"phone": OWNER_DIGITS},  # sem instance
            )

        # Sem instance, nao da pra resolver owner. TASK B lock-down aplica.
        # Caller (_invoke_with_guard) ja tinha rodado deny_if_not_owner antes,
        # entao em producao essa chamada so ocorre com owner ja validado
        # (com instance). Aqui, sem instance, retorna denial.
        assert denial is not None
        assert denial["error"] == "folder_permission_required"


# Import usado no teste
import os
