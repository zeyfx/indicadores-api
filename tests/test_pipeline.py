from datetime import date

from sqlalchemy import func, select

from indicadores.catalogo import INICIO_PADRAO, SERIES
from indicadores.etl.pipeline import executar_series, inicio_incremental
from indicadores.models import ExecucaoEtl, Observacao, Serie


def contar(fabrica, codigo):
    with fabrica() as sessao:
        return sessao.scalar(
            select(func.count()).select_from(Observacao).where(Observacao.serie_codigo == codigo)
        )


def test_primeira_carga_insere_tudo_e_registra_execucao(fabrica, fontes):
    execucoes = executar_series(fabrica, transporte=fontes.transporte)

    assert [e.status for e in execucoes] == ["sucesso"] * len(SERIES)
    ptax = next(e for e in execucoes if e.serie_codigo == "dolar_ptax")
    assert (ptax.extraidas, ptax.inseridas, ptax.atualizadas) == (2, 2, 0)
    assert ptax.desde == INICIO_PADRAO
    assert contar(fabrica, "ipca_mensal") == 3
    with fabrica() as sessao:
        assert sessao.scalar(select(func.count()).select_from(Serie)) == len(SERIES)


def test_reexecucao_e_idempotente(fabrica, fontes):
    executar_series(fabrica, ["ipca_mensal"], transporte=fontes.transporte)
    [segunda] = executar_series(fabrica, ["ipca_mensal"], transporte=fontes.transporte)

    assert (segunda.inseridas, segunda.atualizadas) == (0, 0)
    assert contar(fabrica, "ipca_mensal") == 3


def test_revisao_da_fonte_atualiza_o_valor(fabrica, fontes):
    executar_series(fabrica, ["ipca_mensal"], transporte=fontes.transporte)
    fontes.ibge[63]["202503"] = "0.60"
    fontes.ibge[63]["202504"] = "0.43"

    [execucao] = executar_series(fabrica, ["ipca_mensal"], transporte=fontes.transporte)

    assert (execucao.inseridas, execucao.atualizadas) == (1, 1)
    with fabrica() as sessao:
        assert sessao.get(Observacao, ("ipca_mensal", date(2025, 3, 1))).valor == 0.60


def test_carga_incremental_relê_so_o_fim_da_serie(fabrica, fontes):
    executar_series(fabrica, ["ipca_mensal", "dolar_ptax"], transporte=fontes.transporte)

    with fabrica() as sessao:
        assert inicio_incremental(sessao, SERIES["ipca_mensal"]) == date(2025, 1, 1)
        assert inicio_incremental(sessao, SERIES["dolar_ptax"]) == date(2026, 8, 26)

    fontes.requisicoes.clear()
    executar_series(fabrica, ["dolar_ptax"], transporte=fontes.transporte)
    assert fontes.requisicoes[0].url.params["@dataInicial"] == "'08-26-2026'"


def test_falha_em_uma_serie_nao_impede_as_outras(fabrica, fontes):
    fontes.falhar.add("olinda.bcb.gov.br")

    execucoes = executar_series(fabrica, transporte=fontes.transporte)

    status = {e.serie_codigo: e.status for e in execucoes}
    assert status == {"ipca_mensal": "sucesso", "ipca_indice": "sucesso", "dolar_ptax": "falha"}
    falha = next(e for e in execucoes if e.status == "falha")
    assert "HTTP 503" in falha.erro
    assert falha.finalizada_em is not None
    assert contar(fabrica, "dolar_ptax") == 0
    with fabrica() as sessao:
        assert sessao.scalar(select(func.count()).select_from(ExecucaoEtl)) == 3
