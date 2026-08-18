"""Tests for core.masker module (LGPD PII)."""
from core.masker import mask_pii, has_pii, extract_pii


class TestMaskPII:
    def test_mask_cpf_with_formatting(self):
        text = "Meu CPF e 123.456.789-09"
        masked = mask_pii(text)
        assert "[MASK_CPF]" in masked
        assert "123.456.789-09" not in masked

    def test_mask_cpf_without_formatting(self):
        text = "cpf 12345678909"
        masked = mask_pii(text)
        assert "[MASK_CPF]" in masked

    def test_mask_phone_br(self):
        text = "Ligar para +55 11 98765-4321"
        masked = mask_pii(text)
        assert "[MASK_PHONE_BR]" in masked
        assert "98765" not in masked

    def test_email_not_masked(self):
        """Fix E2 (18/08/2026): EMAIL removido do masker.

        O token [MASK_EMAIL] continha a substring "email", que invertia o
        roteamento deterministico de pedidos de calendario com email de
        participante. Emails agora fluem no texto original.
        """
        text = "Mande email para joao.silva@example.com"
        masked = mask_pii(text)
        assert "joao.silva@example.com" in masked
        assert "[MASK_EMAIL]" not in masked

    def test_mask_credit_card(self):
        text = "Cartao 4111 1111 1111 1111 venceu"
        masked = mask_pii(text)
        assert "[MASK_CARD]" in masked

    def test_mask_cnpj(self):
        text = "CNPJ da empresa: 12.345.678/0001-90"
        masked = mask_pii(text)
        assert "[MASK_CNPJ]" in masked

    def test_mask_rg(self):
        text = "RG: 12.345.678-9"
        masked = mask_pii(text)
        assert "[MASK_RG]" in masked

    def test_no_pii_unchanged(self):
        text = "Oi Jennifer, tudo bem?"
        masked = mask_pii(text)
        assert masked == text

    def test_empty_string(self):
        assert mask_pii("") == ""
        assert mask_pii(None) is None

    def test_multiple_pii_types(self):
        text = "Joao (joao@test.com, CPF 123.456.789-09, tel 11 98765-4321)"
        masked = mask_pii(text)
        assert "joao@test.com" in masked
        assert "[MASK_CPF]" in masked
        assert "[MASK_PHONE_BR]" in masked


class TestHasPII:
    def test_has_pii_true(self):
        assert has_pii("CPF 123.456.789-09") is True
        assert has_pii("Tel +55 11 98765-4321") is True

    def test_has_pii_false(self):
        assert has_pii("Oi tudo bem?") is False
        assert has_pii("Email: test@example.com") is False  # EMAIL nao e mais PII (Fix E2)
        assert has_pii("") is False
        assert has_pii(None) is False


class TestExtractPII:
    def test_extract_cpf(self):
        result = extract_pii("Meu CPF: 123.456.789-09")
        assert "CPF" in result
        assert any("123.456.789-09" in m for m in result["CPF"])

    def test_extract_multiple(self):
        text = "CPF 111.222.333-44 tel 11 99999-8888"
        result = extract_pii(text)
        assert "CPF" in result
        assert "PHONE_BR" in result
