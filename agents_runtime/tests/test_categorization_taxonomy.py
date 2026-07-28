"""Tests for categorizer taxonomy (Fase F4d.6)."""
from agent_orchestration.categorizer import CLASS_VALUES, GROUP_VALUES


def test_class_values_non_empty():
    assert len(CLASS_VALUES) >= 10
    assert "outros" in CLASS_VALUES


def test_group_values_non_empty():
    assert len(GROUP_VALUES) >= 10
    for cls, groups in GROUP_VALUES.items():
        assert len(groups) >= 1


def test_class_values_in_group_dict():
    for cls in CLASS_VALUES:
        assert cls in GROUP_VALUES, f"class {cls} missing from GROUP_VALUES"


def test_each_class_has_at_least_one_group():
    for cls, groups in GROUP_VALUES.items():
        assert len(groups) >= 1


def test_legal_class_covers_cdc():
    assert "legislacao" in GROUP_VALUES["legal"]
    assert "contrato" in GROUP_VALUES["legal"]
    assert "parecer" in GROUP_VALUES["legal"]


def test_edital_class_covers_licitacao():
    assert "licitacao" in GROUP_VALUES["edital"]
    assert "concurso" in GROUP_VALUES["edital"]


def test_academico_class_covers_probabilidade():
    assert "probabilidade" in GROUP_VALUES["academico"]
    assert "livro" in GROUP_VALUES["academico"]
    assert "tese" in GROUP_VALUES["academico"]


def test_empresa_class_covers_processos():
    assert "processos" in GROUP_VALUES["empresa"]
    assert "politica" in GROUP_VALUES["empresa"]


def test_saude_class_covers_protocolo():
    assert "protocolo" in GROUP_VALUES["saude"]
    assert "bula" in GROUP_VALUES["saude"]
    assert "diretrizes" in GROUP_VALUES["saude"]
