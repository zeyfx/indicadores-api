"""Orquestra extração, transformação e carga de cada série, registrando cada execução."""

import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

import httpx
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from indicadores.catalogo import INICIO_PADRAO, SERIES, DefinicaoSerie
from indicadores.config import configuracao
from indicadores.etl.carga import carregar, sincronizar_catalogo
from indicadores.etl.fontes import extrair
from indicadores.etl.transformacao import transformar
from indicadores.models import ExecucaoEtl, Observacao

log = logging.getLogger(__name__)

# Releitura de um trecho já carregado, para capturar revisões das fontes.
MARGEM_DIARIA = timedelta(days=7)
MARGEM_MENSAL_MESES = 2


def inicio_incremental(sessao: Session, definicao: DefinicaoSerie) -> date:
    ultima = sessao.scalar(
        select(func.max(Observacao.data)).where(Observacao.serie_codigo == definicao.codigo)
    )
    if ultima is None:
        return INICIO_PADRAO
    if definicao.frequencia == "mensal":
        inicio = (pd.Timestamp(ultima) - pd.DateOffset(months=MARGEM_MENSAL_MESES)).date()
    else:
        inicio = ultima - MARGEM_DIARIA
    return max(inicio, INICIO_PADRAO)


def executar_serie(
    fabrica: sessionmaker[Session],
    codigo: str,
    cliente: httpx.Client,
    *,
    desde: date | None = None,
    ate: date | None = None,
) -> ExecucaoEtl:
    definicao = SERIES[codigo]
    cfg = configuracao()
    with fabrica() as sessao:
        sincronizar_catalogo(sessao, definicao)
        inicio = desde or inicio_incremental(sessao, definicao)
        execucao = ExecucaoEtl(
            serie_codigo=codigo,
            status="executando",
            iniciada_em=datetime.now(UTC),
            desde=inicio,
            extraidas=0,
            descartadas=0,
            inseridas=0,
            atualizadas=0,
        )
        sessao.add(execucao)
        sessao.commit()

        try:
            bruto = extrair(
                cliente,
                definicao.origem,
                inicio,
                ate or date.today(),
                tentativas=cfg.http_tentativas,
            )
            tabela, descartadas = transformar(definicao.origem, bruto)
            inseridas, atualizadas = carregar(sessao, codigo, tabela)
            execucao.status = "sucesso"
            execucao.extraidas = len(tabela) + descartadas
            execucao.descartadas = descartadas
            execucao.inseridas = inseridas
            execucao.atualizadas = atualizadas
        except Exception as erro:
            sessao.rollback()
            log.exception("ETL de %s falhou", codigo)
            execucao.status = "falha"
            execucao.erro = f"{type(erro).__name__}: {erro}"[:2000]

        execucao.finalizada_em = datetime.now(UTC)
        sessao.commit()
        # Após um rollback os atributos expiram; recarrega para devolver o objeto completo.
        sessao.refresh(execucao)
        log.info(
            "ETL %s: %s (inseridas=%d, atualizadas=%d, descartadas=%d)",
            codigo,
            execucao.status,
            execucao.inseridas,
            execucao.atualizadas,
            execucao.descartadas,
        )
        return execucao


def executar_series(
    fabrica: sessionmaker[Session],
    codigos: Iterable[str] | None = None,
    *,
    transporte: httpx.BaseTransport | None = None,
    desde: date | None = None,
) -> list[ExecucaoEtl]:
    """Roda cada série de forma independente: a falha de uma não interrompe as outras."""
    cfg = configuracao()
    with httpx.Client(
        transport=transporte,
        timeout=cfg.http_timeout,
        headers={"User-Agent": "indicadores-api/0.1"},
    ) as cliente:
        return [
            executar_serie(fabrica, codigo, cliente, desde=desde) for codigo in (codigos or SERIES)
        ]
