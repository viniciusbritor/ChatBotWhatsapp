"""GoldenSet makefile — gera PDFs sinteticos realistas para o smoke.

Uso (a partir de agents_runtime/):

    python -m scripts.build_golden_set

Gera arquivos leves em GoldenSet/:
- cdc-capitulo-1.pdf (Codigo de Defesa do Consumidor, ~30 KB)
- lgpd-capitulo-1.pdf (Lei Geral de Protecao de Dados, ~30 KB)
- manual-higiene.pdf (Manual de higiene das maos, ~20 KB)

Util quando o GoldenSet/ nao tem arquivos reais versionados (padrao
em CI/dev). Os conteudos sao paragraficos sinteticos uteis para
testar extracao, categorizacao e retrieval, nao juridicamente
validados como lei.
"""
from __future__ import annotations

import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ROOT = Path(__file__).resolve().parents[2] / "GoldenSet"


DOCS = [
    {
        "filename": "cdc-capitulo-1.pdf",
        "title": "CDC - Codigo de Defesa do Consumidor - Capitulo 1",
        "paragraphs": [
            "CAPITULO I - DISPOSICOES GERAIS",
            "Art. 1o O presente codigo estabelece normas de protecao e defesa do consumidor, de ordem publica e interesse social, nos termos dos arts. 5o, XXXII, 170, V, da Constituicao Federal.",
            "Art. 2o Consumidor e toda pessoa fisica ou juridica que adquire ou utiliza produto ou servico como destinatario final.",
            "Paragrafo unico. Equipara-se a consumidor a coletividade de pessoas, ainda que indeterminaveis, que haja intervindo nas relacoes de consumo.",
            "Art. 3o Fornecedor e toda pessoa fisica ou juridica, publica ou privada, nacional ou estrangeira, bem como os entes despersonalizados, que desenvolvem atividade de producao, montagem, criacao, construcao, transformacao, importacao, exportacao, distribuicao ou comercializacao de produtos ou prestacao de servicos.",
            "Art. 4o A Politica Nacional das Relacoes de Consumo tem por objetivo o atendimento das necessidades dos consumidores, o respeito a sua dignidade, saude e seguranca, a protecao de seus interesses economicos, a melhoria da sua qualidade de vida, bem como a transparencia e harmonia das relacoes de consumo, atendidos os seguintes principios: I - reconhecimento da vulnerabilidade do consumidor no mercado; II - acao governamental no sentido de proteger efetivamente o consumidor; III - harmonizacao dos interesses dos participantes das relacoes de consumo e compatibilizacao da protecao do consumidor com a necessidade de desenvolvimento economico e tecnologico, de modo a viabilizar os principios nos quais se funda a ordem economica.",
            "CAPITULO II - DA POLITICA NACIONAL DE RELACOES DE CONSUMO",
            "Art. 5o Para a execucao da Politica Nacional das Relacoes de Consumo, os poderes publicos devem envidar esforcos para a) - garantia de produtos e servicos com padrões adequados de qualidade, seguranca, durabilidade e desempenho; b) - adequacao de produtos e servicos as necessidades do consumidor; c) - informacao adequada e clara sobre produtos e servicos, com especificacao correta de quantidade, caracteristicas, composicao, qualidade, preco e garantia; d) - protecao contra a publicidade enganosa e abusiva,_methods comicos desleais ou praticas abusivas.",
        ],
    },
    {
        "filename": "lgpd-capitulo-1.pdf",
        "title": "LGPD - Lei Geral de Protecao de Dados - Capitulo 1",
        "paragraphs": [
            "CAPITULO I - DISPOSICOES PRELIMINARES",
            "Art. 1o Esta Lei dispoe sobre o tratamento de dados pessoais, inclusive nos meios digitais, por pessoa natural ou por pessoa juridica de direito publico ou privado, com o objetivo de proteger os direitos fundamentais de liberdade e de privacidade e o livre desenvolvimento da personalidade da pessoa natural.",
            "Art. 2o A disciplina da protecao de dados pessoais tem como fundamentos: I - o respeito a privacidade; II - a autodeterminacao informativa; III - a liberdade de expressao, de informacao, de comunicacao e de opiniao; IV - a inviolabilidade da intimidade, da honra e da imagem; V - o desenvolvimento economico e tecnologico e a inovacao; VI - a livre iniciativa, a livre concorrencia e a defesa do consumidor; VII - os direitos humanos, o livre desenvolvimento da personalidade, a dignidade e o exercicio da cidadania pelas pessoas naturais.",
            "Art. 3o Esta Lei aplica-se a qualquer operacao de tratamento realizada por pessoa natural ou por pessoa juridica de direito publico ou privado, independentemente do meio, do pais da sede da pessoa ou do pais onde os dados estao localizados, desde que: I - a operacao de tratamento seja realizada no territorio nacional; II - a atividade de tratamento tenha por objeto a oferta ou o fornecimento de bens ou servicos ou o tratamento de dados de individuos localizados no territorio nacional; III - os dados pessoais objeto da operacao de tratamento tenham sido coletados no territorio nacional.",
            "CAPITULO II - DO TRATAMENTO DE DADOS PESSOAIS",
            "Art. 4o Para os fins desta Lei, considera-se: I - dado pessoal: informacao relacionada a pessoa natural identificada ou identificavel; II - dado pessoal sensivel: dado pessoal sobre origem racial ou etnica, conviccao religiosa, opiniao politica, filiacao a sindicato ou a organizacao de caracter religioso, filosofico ou politico, dado referente a saude ou a vida sexual, dado biometrico ou genetico, quando vinculado a pessoa natural.",
        ],
    },
    {
        "filename": "manual-higiene.pdf",
        "title": "Manual de Higiene das Maos - OMS",
        "paragraphs": [
            "PROTOCOLO DE HIGIENE DAS MAOS",
            "1. OBJETIVO",
            "Padronizar os procedimentos de higiene das maos para todos os profissionais de saude, conforme recomendacoes da OMS e da ANVISA.",
            "2. PROCEDIMENTO",
            "2.1 Antes do contato com o paciente: realizar higienizacao das maos com agua e sabao por 40 a 60 segundos, OU friccao com solucao alcoolica 70 por 20 a 30 segundos.",
            "2.2 Apos contato com fluidos corporais: lavar rigorosamente as maos ate os punhos com antisseptico padrao. Secar com papel toalha descartavel.",
            "2.3 Cinco momentos da OMS: (1) Antes de tocar o paciente. (2) Antes de procedimento asseptico. (3) Apos risco de exposicao a fluidos. (4) Apos tocar o paciente. (5) Apos tocar superficies proximas ao paciente.",
            "3. DOCUMENTACAO",
            "Registrar a adesao ao protocolo em formulario institucional diariamente.",
        ],
    },
]


def build_one(filename: str, title: str, paragraphs: list) -> Path:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(
            "reportlab nao instalado. Rode: pip install reportlab"
        ) from exc

    target = ROOT / filename
    c = canvas.Canvas(str(target), pagesize=A4)
    width, height = A4
    y = height - 60
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, y, title)
    y -= 30
    c.setFont("Helvetica", 11)
    for para in paragraphs:
        if y < 60:
            c.showPage()
            c.setFont("Helvetica", 11)
            y = height - 60
        for line in _wrap(para, 90):
            c.drawString(60, y, line)
            y -= 16
        y -= 8
    c.showPage()
    c.save()
    return target


def _wrap(text: str, width_chars: int):
    words = text.split()
    line = ""
    for word in words:
        if len(line) + len(word) + 1 <= width_chars:
            line += " " + word if line else word
        else:
            yield line
            line = word
    if line:
        yield line


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    for spec in DOCS:
        path = build_one(spec["filename"], spec["title"], spec["paragraphs"])
        size_kb = path.stat().st_size / 1024
        logger.info("gerado: %s (%.1f KB)", path.name, size_kb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
