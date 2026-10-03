from dataclasses import dataclass
from datetime import date
from typing import Literal

INICIO_PADRAO = date(2015, 1, 1)


@dataclass(frozen=True)
class AgregadoIbge:
    """Variável de um agregado da API de dados agregados do IBGE (SIDRA), nível Brasil."""

    agregado: int
    variavel: int


@dataclass(frozen=True)
class PtaxBcb:
    """Cotação PTAX do dólar, publicada pelo Banco Central (serviço Olinda)."""

    campo: Literal["cotacaoCompra", "cotacaoVenda"] = "cotacaoVenda"


Origem = AgregadoIbge | PtaxBcb


@dataclass(frozen=True)
class DefinicaoSerie:
    codigo: str
    nome: str
    unidade: str
    frequencia: Literal["diaria", "mensal"]
    fonte: str
    origem: Origem


SERIES: dict[str, DefinicaoSerie] = {
    s.codigo: s
    for s in [
        DefinicaoSerie(
            codigo="ipca_mensal",
            nome="IPCA - variação mensal",
            unidade="%",
            frequencia="mensal",
            fonte="IBGE (agregado 1737)",
            origem=AgregadoIbge(agregado=1737, variavel=63),
        ),
        DefinicaoSerie(
            codigo="ipca_indice",
            nome="IPCA - número-índice (dez/1993 = 100)",
            unidade="índice",
            frequencia="mensal",
            fonte="IBGE (agregado 1737)",
            origem=AgregadoIbge(agregado=1737, variavel=2266),
        ),
        DefinicaoSerie(
            codigo="dolar_ptax",
            nome="Dólar PTAX - venda",
            unidade="R$",
            frequencia="diaria",
            fonte="Banco Central (PTAX)",
            origem=PtaxBcb(campo="cotacaoVenda"),
        ),
    ]
}
