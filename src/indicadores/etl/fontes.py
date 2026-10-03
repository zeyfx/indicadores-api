"""Extração: busca os dados brutos nas APIs públicas, sem interpretar valores."""

import logging
import time
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx

from indicadores.catalogo import AgregadoIbge, Origem, PtaxBcb

log = logging.getLogger(__name__)

URL_IBGE = "https://servicodados.ibge.gov.br/api/v3/agregados"
URL_PTAX = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)


class ErroDeExtracao(RuntimeError):
    pass


def obter_json(
    cliente: httpx.Client,
    url: str,
    params: dict[str, str],
    *,
    tentativas: int = 3,
    espera: Callable[[float], None] = time.sleep,
) -> Any:
    """GET com nova tentativa e espera exponencial em falha de rede ou erro 5xx."""
    for tentativa in range(1, tentativas + 1):
        try:
            resposta = cliente.get(url, params=params)
            if resposta.status_code < 500:
                resposta.raise_for_status()
                return resposta.json()
            motivo = f"HTTP {resposta.status_code}"
        except httpx.TransportError as erro:
            motivo = f"{type(erro).__name__}: {erro}"
        if tentativa < tentativas:
            log.warning("Falha em %s (%s); tentativa %d de %d", url, motivo, tentativa, tentativas)
            espera(2 ** (tentativa - 1))
    raise ErroDeExtracao(f"{url} falhou após {tentativas} tentativas ({motivo})")


def extrair_ibge(
    cliente: httpx.Client, origem: AgregadoIbge, desde: date, ate: date, **opcoes: Any
) -> dict[str, str]:
    """Devolve {"AAAAMM": "valor"} da variável no nível Brasil."""
    periodos = f"{desde:%Y%m}-{ate:%Y%m}"
    url = f"{URL_IBGE}/{origem.agregado}/periodos/{periodos}/variaveis/{origem.variavel}"
    dados = obter_json(cliente, url, {"localidades": "N1[all]"}, **opcoes)
    try:
        return dict(dados[0]["resultados"][0]["series"][0]["serie"])
    except (IndexError, KeyError, TypeError) as erro:
        raise ErroDeExtracao(f"Resposta do IBGE fora do formato esperado: {erro!r}") from erro


def extrair_ptax(
    cliente: httpx.Client, origem: PtaxBcb, desde: date, ate: date, **opcoes: Any
) -> list[dict[str, Any]]:
    """Devolve a lista de cotações [{"dataHoraCotacao": ..., campo: ...}] do período."""
    params = {
        "@dataInicial": f"'{desde:%m-%d-%Y}'",
        "@dataFinalCotacao": f"'{ate:%m-%d-%Y}'",
        "$format": "json",
        "$select": f"{origem.campo},dataHoraCotacao",
    }
    dados = obter_json(cliente, URL_PTAX, params, **opcoes)
    if not isinstance(dados, dict) or not isinstance(dados.get("value"), list):
        raise ErroDeExtracao("Resposta do PTAX fora do formato esperado: falta a lista 'value'")
    return dados["value"]


def extrair(cliente: httpx.Client, origem: Origem, desde: date, ate: date, **opcoes: Any) -> Any:
    match origem:
        case AgregadoIbge():
            return extrair_ibge(cliente, origem, desde, ate, **opcoes)
        case PtaxBcb():
            return extrair_ptax(cliente, origem, desde, ate, **opcoes)
    raise TypeError(f"Origem desconhecida: {origem!r}")
