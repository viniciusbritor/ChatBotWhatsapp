from unittest.mock import patch

from core.auth import _is_valid_firebase_jwt, is_path_protected


def test_oauth_start_is_protected_and_callback_is_public():
    assert is_path_protected("/oauth/google") is True
    assert is_path_protected("/oauth/callback") is False


def test_pubsub_push_is_public_oidc_validated():
    assert is_path_protected("/pubsub/push") is False


def test_admin_chat_version_stay_protected():
    assert is_path_protected("/admin/agents") is True
    assert is_path_protected("/chat") is True
    assert is_path_protected("/version") is True


def test_valid_firebase_token_requires_verified_claims():
    with patch(
        "core.auth.id_token.verify_firebase_token",
        return_value={"sub": "firebase-user-1"},
    ) as verify:
        assert _is_valid_firebase_jwt("signed-token") is True
    assert verify.call_args.kwargs["audience"] == "coherence-ominichannel-fs"


def test_firebase_token_rejects_verification_failure():
    with patch(
        "core.auth.id_token.verify_firebase_token",
        side_effect=ValueError("invalid signature"),
    ):
        assert _is_valid_firebase_jwt("forged-token") is False


def test_firebase_token_rejects_missing_subject():
    with patch(
        "core.auth.id_token.verify_firebase_token",
        return_value={"email": "masked@example.com"},
    ):
        assert _is_valid_firebase_jwt("signed-token") is False
