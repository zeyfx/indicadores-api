"""Transformação: converte o formato de cada fonte em uma tabela única (data, valor) validada."""

from typing import Any

import numpy as np
import pandas as pd

from indicadores.catalogo import AgregadoIbge, Origem, PtaxBcb

# Símbolos do IBGE para valor inexistente, não disponível ou sigiloso.
AUSENTES_IBGE = ["...", "..", "-", "X", ""]


def ibge_para_tabela(serie: dict[str, str]) -> pd.DataFrame:
    bruto = pd.DataFrame(list(serie.items()), columns=["periodo", "valor"])
    return pd.DataFrame(
        {
            "data": pd.to_datetime(bruto["periodo"], format="%Y%m", errors="coerce").dt.date,
            "valor": pd.to_numeric(bruto["valor"].replace(AUSENTES_IBGE, None), errors="coerce"),
        }
    )


def ptax_para_tabela(registros: list[dict[str, Any]], campo: str) -> pd.DataFrame:
    bruto = pd.DataFrame(registros, columns=["dataHoraCotacao", campo])
    momento = pd.to_datetime(bruto["dataHoraCotacao"], format="mixed", errors="coerce")
    tabela = pd.DataFrame(
        {"momento": momento, "valor": pd.to_numeric(bruto[campo], errors="coerce")}
    )
    # Mais de uma cotação no mesmo dia: a ordenação faz a última do dia prevalecer na validação.
    tabela = tabela.sort_values("momento", kind="stable", na_position="first")
    tabela["data"] = tabela["momento"].dt.date
    return tabela[["data", "valor"]]


def validar(tabela: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove linhas sem data ou valor, valores não finitos e datas repetidas (fica a última)."""
    total = len(tabela)
    limpa = tabela.dropna(subset=["data", "valor"])
    limpa = limpa[np.isfinite(limpa["valor"].astype(float))]
    limpa = (
        limpa.drop_duplicates(subset="data", keep="last").sort_values("data").reset_index(drop=True)
    )
    return limpa, total - len(limpa)


def transformar(origem: Origem, bruto: Any) -> tuple[pd.DataFrame, int]:
    match origem:
        case AgregadoIbge():
            tabela = ibge_para_tabela(bruto)
        case PtaxBcb():
            tabela = ptax_para_tabela(bruto, origem.campo)
        case _:
            raise TypeError(f"Origem desconhecida: {origem!r}")
    return validar(tabela)
