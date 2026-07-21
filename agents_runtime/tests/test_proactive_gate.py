"""Tests for proactive_gate module."""
import pytest
from datetime import datetime, timezone, timedelta


class TestProhibitedTemplates:
    def test_greeting_only_prohibited(self):
        from core.proactive_gate import is_prohibited_template
        assert is_prohibited_template("Oi tudo bem?") is True
        assert is_prohibited_template("oi, tudo bem?") is True

    def test_senti_falta_prohibited(self):
        from core.proactive_gate import is_prohibited_template
        assert is_prohibited_template("Senti sua falta!") is True

    def test_elogio_forcado_prohibited(self):
        from core.proactive_gate import is_prohibited_template
        assert is_prohibited_template("Voce e incrivel!") is True

    def test_bom_dia_prohibited(self):
        from core.proactive_gate import is_prohibited_template
        assert is_prohibited_template("Bom dia!") is True

    def test_conteudo_relevante_allowed(self):
        from core.proactive_gate import is_prohibited_template
        assert is_prohibited_template("Sua reuniao comeca em 1h. Confia!") is False

    def test_tip_construtivo_allowed(self):
        from core.proactive_gate import is_prohibited_template
        assert is_prohibited_template("Lembrete: dentista amanha 14h") is False


class TestCheckDM:
    def test_phone_not_in_allowlist(self):
        from core.proactive_gate import check, ALLOWLIST
        allowed, reason = check("+5511988887777", relevance_score=0.9)
        if "+5511988887777" not in ALLOWLIST:
            assert allowed is False
            assert reason == "not_in_allowlist"

    def test_user_opted_out(self):
        from core.proactive_gate import check, ALLOWLIST
        if not ALLOWLIST:
            pytest.skip("ALLOWLIST empty")
        master = ALLOWLIST[0]
        allowed, reason = check(
            master,
            contact_state={"proactive_opt_out": True},
            relevance_score=0.9,
        )
        assert allowed is False
        assert reason == "user_opt_out"

    def test_user_mode_off(self):
        from core.proactive_gate import check, ALLOWLIST
        if not ALLOWLIST:
            pytest.skip("ALLOWLIST empty")
        master = ALLOWLIST[0]
        allowed, reason = check(
            master,
            contact_state={"proactive_mode": "off"},
            relevance_score=0.9,
        )
        assert allowed is False
        assert reason == "user_set_off"

    def test_low_relevance(self):
        from core.proactive_gate import check, ALLOWLIST, MIN_RELEVANCE
        if not ALLOWLIST:
            pytest.skip("ALLOWLIST empty")
        master = ALLOWLIST[0]
        allowed, reason = check(
            master,
            contact_state={},
            relevance_score=MIN_RELEVANCE - 0.1,
        )
        assert allowed is False
        assert "low_relevance" in reason

    def test_max_per_contact_day(self):
        from core.proactive_gate import check, ALLOWLIST, MAX_PER_CONTACT_DAY
        if not ALLOWLIST:
            pytest.skip("ALLOWLIST empty")
        master = ALLOWLIST[0]
        allowed, reason = check(
            master,
            contact_state={"proactive_messages_today": MAX_PER_CONTACT_DAY},
            relevance_score=0.9,
        )
        assert allowed is False
        assert reason == "max_per_contact_day"

    def test_cooldown_active(self):
        from core.proactive_gate import check, ALLOWLIST
        if not ALLOWLIST:
            pytest.skip("ALLOWLIST empty")
        master = ALLOWLIST[0]
        future = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        allowed, reason = check(
            master,
            contact_state={"proactive_cooldown_until": future},
            relevance_score=0.9,
        )
        assert allowed is False
        assert reason == "cooldown_active"

    def test_engagement_paused(self):
        from core.proactive_gate import check, ALLOWLIST
        if not ALLOWLIST:
            pytest.skip("ALLOWLIST empty")
        master = ALLOWLIST[0]
        future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        allowed, reason = check(
            master,
            contact_state={"proactive_paused_until": future},
            relevance_score=0.9,
        )
        assert allowed is False
        assert reason == "engagement_paused"


class TestCheckGroup:
    def test_non_member_blocked(self):
        from core.proactive_gate import check, ALLOWLIST
        if not ALLOWLIST:
            pytest.skip("ALLOWLIST empty")
        allowed, reason = check(
            "+5511988887777",
            group_jid="120363123456@g.us",
            is_group_member=False,
            relevance_score=0.9,
        )
        assert allowed is False

    def test_member_allowed(self):
        from core.proactive_gate import check, ALLOWLIST
        if not ALLOWLIST:
            pytest.skip("ALLOWLIST empty")
        member = "+5511966830020"
        if member not in ALLOWLIST:
            allowed, reason = check(
                member,
                group_jid="120363123456@g.us",
                is_group_member=True,
                relevance_score=0.9,
            )
            assert "quiet_hours" in reason or allowed is True


class TestGetConfig:
    def test_returns_dict(self):
        from core.proactive_gate import get_config
        config = get_config()
        assert "allowlist" in config
        assert "max_per_contact_day" in config
        assert "max_global_day" in config
        assert "cooldown_hours" in config


class TestKillSwitch:
    def test_disable(self):
        from core.proactive_gate import set_kill_switch, check, ALLOWLIST
        if not ALLOWLIST:
            pytest.skip("ALLOWLIST empty")
        set_kill_switch(True)
        allowed, reason = check(ALLOWLIST[0], relevance_score=0.9)
        assert allowed is False
        assert reason == "kill_switch_global"
        set_kill_switch(False)
