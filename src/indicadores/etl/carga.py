"""Carga: grava só o que é novo ou mudou, com upsert idempotente."""

import math
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from indicadores.catalogo import DefinicaoSerie
from indicadores.models import Observacao, Serie

TAMANHO_DO_LOTE = 500


def sincronizar_catalogo(sessao: Session, definicao: DefinicaoSerie) -> None:
    sessao.merge(
        Serie(
            codigo=definicao.codigo,
            nome=definicao.nome,
            unidade=definicao.unidade,
            frequencia=definicao.frequencia,
            fonte=definicao.fonte,
        )
    )


def _upsert(sessao: Session, linhas: list[dict]) -> None:
    dialeto = sessao.get_bind().dialect.name
    if dialeto == "postgresql":
        insert = postgresql.insert
    elif dialeto == "sqlite":
        insert = sqlite.insert
    else:
        raise NotImplementedError(f"Upsert não implementado para o banco {dialeto}")

    for inicio in range(0, len(linhas), TAMANHO_DO_LOTE):
        comando = insert(Observacao).values(linhas[inicio : inicio + TAMANHO_DO_LOTE])
        comando = comando.on_conflict_do_update(
            index_elements=[Observacao.serie_codigo, Observacao.data],
            set_={"valor": comando.excluded.valor, "carregado_em": comando.excluded.carregado_em},
        )
        sessao.execute(comando)


def carregar(sessao: Session, codigo: str, tabela: pd.DataFrame) -> tuple[int, int]:
    """Compara com o que já está no banco e devolve (inseridas, atualizadas)."""
    if tabela.empty:
        return 0, 0

    existentes = dict(
        sessao.execute(
            select(Observacao.data, Observacao.valor).where(
                Observacao.serie_codigo == codigo,
                Observacao.data.between(tabela["data"].min(), tabela["data"].max()),
            )
        ).all()
    )

    agora = datetime.now(UTC)
    inseridas = atualizadas = 0
    linhas = []
    for data, valor in zip(tabela["data"], tabela["valor"], strict=True):
        valor = float(valor)
        anterior = existentes.get(data)
        if anterior is None:
            inseridas += 1
        elif math.isclose(anterior, valor, rel_tol=0, abs_tol=1e-9):
            continue
        else:
            atualizadas += 1
        linhas.append({"serie_codigo": codigo, "data": data, "valor": valor, "carregado_em": agora})

    if linhas:
        _upsert(sessao, linhas)
    return inseridas, atualizadas
