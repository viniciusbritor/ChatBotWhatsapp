"""Re-ingerir PDF na base REAL do Firestore (PT7 F4-D).

Container-friendly: textos inline (sem dependencia de GoldenSet/).
Em prod, a imagem base (gcr.io/.../agents-runtime) tem o codigo mas
nao tem o GoldenSet. Este script carrega texto inline (nao arquivo)
e indexa no Firestore real.

Texto fonte: CDC (Codigo de Defesa do Consumidor), LGPD e
Manual de Higiene das Maos - disponivel publicamente.

Uso (Cloud Run Job):
    python -m scripts.reindex_golden_set
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


PHONE = "5511966830020"
PROJECT = "coherence-ominichannel-fs"


CDC_TEXT = """CAPITULO I - DISPOSICOES GERAIS

Art. 1o O presente codigo estabelece normas de protecao e defesa do consumidor, de ordem publica e interesse social, nos termos dos arts. 5o, XXXII, 170, V, da Constituicao Federal e art. 48 e seu paragrafo IV das Disposicoes Constitucionais Transitórias.

Art. 2o Consumidor e toda pessoa fisica ou juridica que adquire ou utiliza produto ou servico como destinatario final.

Paragrafo unico. Equipara-se a consumidor a coletividade de pessoas, ainda que indeterminaveis, que haja intervindo nas relacoes de consumo.

Art. 3o Fornecedor e toda pessoa fisica ou juridica, publica ou privada, nacional ou estrangeira, bem como os entes despersonalizados, que desenvolvem atividade de producao, montagem, criacao, construcao, transformacao, importacao, exportacao, distribuicao ou comercializacao de produtos ou prestacao de servicos.

Art. 4o A Politica Nacional das Relacoes de Consumo tem por objetivo o atendimento das necessidades dos consumidores, o respeito a sua dignidade, saude e seguranca, a protecao de seus interesses economicos, a melhoria da sua qualidade de vida, bem como a transparencia e harmonia das relacoes de consumo.

CAPITULO II - DA POLITICA NACIONAL DE RELACOES DE CONSUMO

Art. 5o Para a execucao da Politica Nacional das Relacoes de Consumo, os poderes publicos devem envidar esforcos para a) - garantia de produtos e servicos com padrões adequados de qualidade, seguranca, durabilidade e desempenho; b) - adequacao de produtos e servicos as necessidades do consumidor; c - informacao adequada e clara sobre produtos e servicos, com especificacao correta de quantidade, caracteristicas, composicao, qualidade, preco e garantia; d - protecao contra a publicidade enganosa e abusiva.

CAPITULO III - DA PUBLICIDADE

Art. 36 A publicidade deve ser veiculada de tal forma que o consumidor, facil e imediatamente a identifique como tal. O fornecedor, na publicidade de seus produtos ou servicos, mantendraa em seu poder, para informacao dos legitimos interessados, os dados fáticos, tecnicos e cientificos que do sustentacao a mensagem."""


LGPD_TEXT = """CAPITULO I - DISPOSICOES PRELIMINARES

Art. 1o Esta Lei dispoe sobre o tratamento de dados pessoais, inclusive nos meios digitais, por pessoa natural ou por pessoa juridica de direito publico ou privado, com o objetivo de proteger os direitos fundamentais de liberdade e de privacidade e o livre desenvolvimento da personalidade da pessoa natural.

Art. 2o A disciplina da protecao de dados pessoais tem como fundamentos: I - o respeito a privacidade; II - a autodeterminacao informativa; III - a liberdade de expressao, de informacao, de comunicacao e de opiniao; IV - a inviolabilidade da intimidade, da honra e da imagem; V - o desenvolvimento economico e tecnologico e a inovacao; VI - a livre iniciativa, a livre concorrencia e a defesa do consumidor; VII - os direitos humanos, o livre desenvolvimento da personalidade, a dignidade e o exercicio da cidadania pelas pessoas naturais.

Art. 3o Esta Lei aplica-se a qualquer operacao de tratamento realizada por pessoa natural ou por pessoa juridica de direito publico ou privado, independentemente do meio, do pais da sede da pessoa ou do pais onde os dados estao localizados, desde que a operacao de tratamento seja realizada no territorio nacional ou tenha por objeto a oferta ou o fornecimento de bens ou servicos ou o tratamento de dados de individuos localizados no territorio nacional.

CAPITULO II - DO TRATAMENTO DE DADOS PESSOAIS

Art. 4o Para os fins desta Lei, considera-se: I - dado pessoal: informacao relacionada a pessoa natural identificada ou identificavel; II - dado pessoal sensivel: dado pessoal sobre origem racial ou etnica, conviccao religiosa, opiniao politica, filiacao a sindicato, dado referente a saude ou a vida sexual, dado biometrico."""


HIGIENE_TEXT = """PROTOCOLO DE HIGIENE DAS MAOS

1. OBJETIVO - Padronizar os procedimentos de higiene das maos para todos os profissionais de saude, conforme recomendacoes da OMS e da ANVISA.

2. PROCEDIMENTO

2.1 Antes do contato com o paciente: realizar higienizacao das maos com agua e sabao por 40 a 60 segundos, OU friccao com solucao alcoolica 70 por 20 a 30 segundos.

2.2 Apos contato com fluidos corporais: lavar rigorosamente as maos ate os punhos com antisseptico padrao. Secar com papel toalha descartavel.

2.3 Cinco momentos da OMS: (1) Antes de tocar o paciente. (2) Antes de procedimento asseptico. (3) Apos risco de exposicao a fluidos. (4) Apos tocar o paciente. (5) Apos tocar superficies proximas ao paciente.

3. DOCUMENTACAO - Registrar a adesao ao protocolo em formulario institucional diariamente."""


DOCS = [
    {"name": "cdc-capitulo-1.pdf", "text": CDC_TEXT, "category": "legal", "klass": "legal", "group": "legislacao", "theme": "cdc"},
    {"name": "lgpd-capitulo-1.pdf", "text": LGPD_TEXT, "category": "legal", "klass": "legal", "group": "legislacao", "theme": "lgpd"},
]


def main() -> int:
    os.environ.setdefault("GCP_PROJECT", PROJECT)
    from core.rag import index_private_document

    failures = 0
    for spec in DOCS:
        text = spec["text"].strip()
        if len(text) < 100:
            logger.warning("%s muito curto (%d chars), skip", spec["name"], len(text))
            continue
        try:
            logger.info("Indexando %s (%d chars, class=%s)", spec["name"], len(text), spec["klass"])
            result = asyncio.run(index_private_document(
                phone=PHONE,
                text_content=text,
                source_title=spec["name"],
                category=spec["category"],
                class_=spec["klass"],
                group=spec["group"],
                theme=spec["theme"],
                metadata={
                    "filename": spec["name"],
                    "mime_type": "application/pdf",
                    "test_run": True,
                    "reindex_pt7": True,
                },
            ))
            if result.get("error"):
                logger.warning("  Erro: %s", result["error"])
                failures += 1
            else:
                logger.info(
                    "  OK chunks=%s chunks_indexed=%s",
                    result.get("chunks"),
                    result.get("chunks_indexed"),
                )
        except Exception as exc:
            logger.error("Falha ao indexar %s: %s", spec["name"], exc)
            failures += 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
