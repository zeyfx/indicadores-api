from datetime import UTC, date, datetime

import pytest

from indicadores.etl.pipeline import executar_series
from indicadores.models import Observacao, Serie


@pytest.fixture
def carregado(fabrica, fontes):
    executar_series(fabrica, transporte=fontes.transporte)


def inserir_indice_ipca(fabrica, valores: dict[date, float]):
    with fabrica() as sessao:
        sessao.merge(
            Serie(
                codigo="ipca_indice",
                nome="IPCA",
                unidade="índice",
                frequencia="mensal",
                fonte="teste",
            )
        )
        sessao.flush()  # a série precisa existir antes das observações (chave estrangeira)
        for dia, valor in valores.items():
            sessao.add(
                Observacao(
                    serie_codigo="ipca_indice",
                    data=dia,
                    valor=valor,
                    carregado_em=datetime.now(UTC),
                )
            )
        sessao.commit()


def test_saude(cliente):
    assert cliente.get("/saude").json() == {"status": "ok"}


def test_lista_series_com_cobertura(cliente, carregado):
    series = {s["codigo"]: s for s in cliente.get("/series").json()}

    assert set(series) == {"ipca_mensal", "ipca_indice", "dolar_ptax"}
    assert series["dolar_ptax"]["total_observacoes"] == 2
    assert series["dolar_ptax"]["primeira_data"] == "2026-09-01"
    assert series["dolar_ptax"]["ultima_data"] == "2026-09-02"


def test_observacoes_filtradas_por_periodo(cliente, carregado):
    resposta = cliente.get(
        "/series/ipca_mensal/observacoes", params={"inicio": "2025-02-01", "fim": "2025-03-31"}
    )

    assert resposta.json() == [
        {"data": "2025-02-01", "valor": 1.31},
        {"data": "2025-03-01", "valor": 0.56},
    ]


def test_serie_inexistente_da_404(cliente):
    assert cliente.get("/series/selic/observacoes").status_code == 404


def test_periodo_invertido_da_422(cliente, carregado):
    resposta = cliente.get(
        "/series/ipca_mensal/observacoes", params={"inicio": "2025-03-01", "fim": "2025-01-01"}
    )
    assert resposta.status_code == 422


def test_resumo_calcula_estatisticas_e_variacao(cliente, carregado):
    resumo = cliente.get("/series/dolar_ptax/resumo").json()

    assert resumo["observacoes"] == 2
    assert resumo["primeiro_valor"] == 5.10
    assert resumo["ultimo_valor"] == 5.12
    assert resumo["media"] == pytest.approx(5.11)
    assert resumo["variacao_percentual"] == pytest.approx(0.3922, abs=1e-4)


def test_resumo_nao_calcula_variacao_de_serie_em_percentual(cliente, carregado):
    assert cliente.get("/series/ipca_mensal/resumo").json()["variacao_percentual"] is None


def test_agregado_mensal_e_anual(cliente, carregado):
    mensal = cliente.get("/series/dolar_ptax/agregado", params={"periodo": "mensal"}).json()
    anual = cliente.get("/series/ipca_mensal/agregado", params={"periodo": "anual"}).json()

    assert mensal == [
        {"periodo": "2026-09", "observacoes": 2, "media": 5.11, "minimo": 5.10, "maximo": 5.12}
    ]
    assert anual[0]["periodo"] == "2025"
    assert anual[0]["observacoes"] == 3


def test_ipca_12m_usa_janela_mensal_mesmo_com_mes_faltante(cliente, fabrica):
    valores = {date(2024, m, 1): 100.0 + m for m in range(1, 13)}
    valores.update({date(2025, 1, 1): 110.0, date(2025, 3, 1): 115.0})  # fev/2025 faltando
    inserir_indice_ipca(fabrica, valores)

    resposta = cliente.get("/indicadores/ipca-12m", params={"inicio": "2025-01-01"}).json()

    # jan/2025 contra jan/2024 (101) e mar/2025 contra mar/2024 (103); fev não tem dado.
    assert resposta == [
        {"data": "2025-01-01", "acumulado_12m": round((110 / 101 - 1) * 100, 2)},
        {"data": "2025-03-01", "acumulado_12m": round((115 / 103 - 1) * 100, 2)},
    ]


def test_disparo_do_etl_exige_chave(cliente):
    assert cliente.post("/etl/execucoes", json={}).status_code == 401
    resposta = cliente.post("/etl/execucoes", json={}, headers={"X-API-Key": "errada"})
    assert resposta.status_code == 401


def test_disparo_do_etl_desligado_sem_chave_configurada(cliente, monkeypatch):
    from indicadores.config import configuracao

    monkeypatch.delenv("ETL_API_KEY")
    configuracao.cache_clear()

    resposta = cliente.post("/etl/execucoes", json={}, headers={"X-API-Key": "segredo"})
    assert resposta.status_code == 503


def test_disparo_do_etl_rejeita_serie_desconhecida(cliente):
    resposta = cliente.post(
        "/etl/execucoes", json={"series": ["selic"]}, headers={"X-API-Key": "segredo"}
    )
    assert resposta.status_code == 422


def test_disparo_do_etl_roda_em_segundo_plano_e_registra(cliente):
    resposta = cliente.post(
        "/etl/execucoes", json={"series": ["dolar_ptax"]}, headers={"X-API-Key": "segredo"}
    )

    assert resposta.status_code == 202
    execucoes = cliente.get("/etl/execucoes", params={"serie": "dolar_ptax"}).json()
    assert len(execucoes) == 1
    assert execucoes[0]["status"] == "sucesso"
    assert execucoes[0]["inseridas"] == 2
