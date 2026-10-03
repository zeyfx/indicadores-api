import secrets
from collections.abc import Iterator
from datetime import date
from typing import Annotated, Literal

import httpx
import pandas as pd
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import Select, extract, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from indicadores.api.esquemas import (
    AgregadoSaida,
    ExecucaoAgendada,
    ExecucaoSaida,
    Ipca12mSaida,
    ObservacaoSaida,
    PedidoDeExecucao,
    ResumoSaida,
    SerieSaida,
)
from indicadores.catalogo import SERIES
from indicadores.config import configuracao
from indicadores.db import abrir_sessao, obter_fabrica
from indicadores.etl.pipeline import executar_series
from indicadores.models import ExecucaoEtl, Observacao, Serie

rotas = APIRouter()


def obter_sessao(
    fabrica: Annotated[sessionmaker[Session], Depends(obter_fabrica)],
) -> Iterator[Session]:
    yield from abrir_sessao(fabrica)


def obter_transporte() -> httpx.BaseTransport | None:
    """Transporte HTTP do ETL; None usa a rede. Os testes injetam um transporte falso."""
    return None


SessaoDep = Annotated[Session, Depends(obter_sessao)]
Inicio = Annotated[date | None, Query(description="Data inicial (inclusive)")]
Fim = Annotated[date | None, Query(description="Data final (inclusive)")]


def _serie_ou_404(sessao: Session, codigo: str) -> Serie:
    serie = sessao.get(Serie, codigo)
    if serie is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Série '{codigo}' não encontrada")
    return serie


def _filtrar_periodo(consulta: Select, codigo: str, inicio: date | None, fim: date | None):
    if inicio and fim and inicio > fim:
        raise HTTPException(422, "inicio deve ser <= fim")
    consulta = consulta.where(Observacao.serie_codigo == codigo)
    if inicio:
        consulta = consulta.where(Observacao.data >= inicio)
    if fim:
        consulta = consulta.where(Observacao.data <= fim)
    return consulta


@rotas.get("/saude", tags=["infra"])
def saude(sessao: SessaoDep) -> dict[str, str]:
    sessao.execute(text("SELECT 1"))
    return {"status": "ok"}


@rotas.get("/series", response_model=list[SerieSaida], tags=["séries"])
def listar_series(sessao: SessaoDep):
    consulta = (
        select(
            Serie,
            func.count(Observacao.data),
            func.min(Observacao.data),
            func.max(Observacao.data),
        )
        .outerjoin(Observacao, Observacao.serie_codigo == Serie.codigo)
        .group_by(Serie.codigo)
        .order_by(Serie.codigo)
    )
    return [
        SerieSaida.model_validate(serie).model_copy(
            update={"total_observacoes": total, "primeira_data": primeira, "ultima_data": ultima}
        )
        for serie, total, primeira, ultima in sessao.execute(consulta)
    ]


@rotas.get("/series/{codigo}/observacoes", response_model=list[ObservacaoSaida], tags=["séries"])
def listar_observacoes(
    codigo: str,
    sessao: SessaoDep,
    inicio: Inicio = None,
    fim: Fim = None,
    limite: Annotated[int, Query(ge=1, le=10_000)] = 1_000,
):
    _serie_ou_404(sessao, codigo)
    consulta = _filtrar_periodo(select(Observacao), codigo, inicio, fim)
    return sessao.scalars(consulta.order_by(Observacao.data).limit(limite)).all()


@rotas.get("/series/{codigo}/resumo", response_model=ResumoSaida, tags=["análises"])
def resumir(codigo: str, sessao: SessaoDep, inicio: Inicio = None, fim: Fim = None):
    serie = _serie_ou_404(sessao, codigo)
    agregados = select(
        func.count(Observacao.data),
        func.min(Observacao.data),
        func.max(Observacao.data),
        func.min(Observacao.valor),
        func.max(Observacao.valor),
        func.avg(Observacao.valor),
    )
    total, primeira, ultima, minimo, maximo, media = sessao.execute(
        _filtrar_periodo(agregados, codigo, inicio, fim)
    ).one()

    def valor_em(dia: date | None) -> float | None:
        if dia is None:
            return None
        return sessao.scalar(
            select(Observacao.valor).where(
                Observacao.serie_codigo == codigo, Observacao.data == dia
            )
        )

    primeiro, ultimo = valor_em(primeira), valor_em(ultima)
    variacao = None
    if serie.unidade != "%" and primeiro and ultimo is not None:
        variacao = round((ultimo / primeiro - 1) * 100, 4)

    return ResumoSaida(
        serie=codigo,
        observacoes=total,
        primeira_data=primeira,
        ultima_data=ultima,
        primeiro_valor=primeiro,
        ultimo_valor=ultimo,
        minimo=minimo,
        maximo=maximo,
        media=None if media is None else round(float(media), 6),
        variacao_percentual=variacao,
    )


@rotas.get("/series/{codigo}/agregado", response_model=list[AgregadoSaida], tags=["análises"])
def agregar(
    codigo: str,
    sessao: SessaoDep,
    periodo: Literal["mensal", "anual"] = "mensal",
    inicio: Inicio = None,
    fim: Fim = None,
):
    _serie_ou_404(sessao, codigo)
    grupos = [extract("year", Observacao.data).label("ano")]
    if periodo == "mensal":
        grupos.append(extract("month", Observacao.data).label("mes"))

    consulta = select(
        *grupos,
        func.count(Observacao.data),
        func.avg(Observacao.valor),
        func.min(Observacao.valor),
        func.max(Observacao.valor),
    )
    consulta = _filtrar_periodo(consulta, codigo, inicio, fim).group_by(*grupos).order_by(*grupos)

    saida = []
    for linha in sessao.execute(consulta):
        *chave, total, media, minimo, maximo = linha
        rotulo = f"{int(chave[0]):04d}" + (f"-{int(chave[1]):02d}" if len(chave) == 2 else "")
        saida.append(
            AgregadoSaida(
                periodo=rotulo,
                observacoes=total,
                media=round(float(media), 6),
                minimo=minimo,
                maximo=maximo,
            )
        )
    return saida


@rotas.get("/indicadores/ipca-12m", response_model=list[Ipca12mSaida], tags=["análises"])
def ipca_acumulado_12m(sessao: SessaoDep, inicio: Inicio = None, fim: Fim = None):
    """IPCA acumulado em 12 meses, calculado a partir do número-índice."""
    _serie_ou_404(sessao, "ipca_indice")
    if inicio and fim and inicio > fim:
        raise HTTPException(422, "inicio deve ser <= fim")
    desde = (pd.Timestamp(inicio) - pd.DateOffset(months=12)).date() if inicio else None
    consulta = _filtrar_periodo(
        select(Observacao.data, Observacao.valor), "ipca_indice", desde, fim
    ).order_by(Observacao.data)
    linhas = sessao.execute(consulta).all()
    if not linhas:
        return []

    indice = pd.Series(
        [valor for _, valor in linhas],
        index=pd.DatetimeIndex([dia for dia, _ in linhas]),
    )
    # Reindexa mês a mês para que um mês faltante não desloque a janela de 12 meses.
    indice = indice.asfreq("MS")
    acumulado = ((indice / indice.shift(12) - 1) * 100).dropna()
    if inicio:
        acumulado = acumulado[acumulado.index >= pd.Timestamp(inicio)]
    return [
        Ipca12mSaida(data=momento.date(), acumulado_12m=round(float(valor), 2))
        for momento, valor in acumulado.items()
    ]


@rotas.get("/etl/execucoes", response_model=list[ExecucaoSaida], tags=["etl"])
def listar_execucoes(
    sessao: SessaoDep,
    serie: str | None = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 50,
):
    consulta = select(ExecucaoEtl).order_by(ExecucaoEtl.id.desc()).limit(limite)
    if serie:
        consulta = consulta.where(ExecucaoEtl.serie_codigo == serie)
    return sessao.scalars(consulta).all()


@rotas.post(
    "/etl/execucoes",
    response_model=ExecucaoAgendada,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["etl"],
)
def disparar_etl(
    pedido: PedidoDeExecucao,
    tarefas: BackgroundTasks,
    fabrica: Annotated[sessionmaker[Session], Depends(obter_fabrica)],
    transporte: Annotated[httpx.BaseTransport | None, Depends(obter_transporte)],
    x_api_key: Annotated[str | None, Header()] = None,
):
    chave = configuracao().etl_api_key
    if not chave:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Disparo pela API desativado")
    if not x_api_key or not secrets.compare_digest(x_api_key, chave):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave de API inválida")

    series = pedido.series or list(SERIES)
    desconhecidas = sorted(set(series) - set(SERIES))
    if desconhecidas:
        raise HTTPException(422, f"Séries desconhecidas: {desconhecidas}")

    tarefas.add_task(executar_series, fabrica, series, transporte=transporte, desde=pedido.desde)
    return ExecucaoAgendada(series=series, mensagem="ETL agendado; acompanhe em GET /etl/execucoes")
