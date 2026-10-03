from datetime import date

import httpx
import pytest

from indicadores.catalogo import AgregadoIbge, PtaxBcb
from indicadores.etl.fontes import ErroDeExtracao, extrair, obter_json


def test_ibge_monta_url_com_periodos_e_nivel_brasil(fontes):
    with httpx.Client(transport=fontes.transporte) as cliente:
        serie = extrair(cliente, AgregadoIbge(1737, 63), date(2025, 1, 15), date(2025, 3, 2))

    assert serie == fontes.ibge[63]
    url = fontes.requisicoes[0].url
    assert url.path == "/api/v3/agregados/1737/periodos/202501-202503/variaveis/63"
    assert url.params["localidades"] == "N1[all]"


def test_ptax_envia_datas_no_formato_odata(fontes):
    with httpx.Client(transport=fontes.transporte) as cliente:
        registros = extrair(cliente, PtaxBcb(), date(2026, 9, 1), date(2026, 9, 30))

    assert registros == fontes.ptax
    params = fontes.requisicoes[0].url.params
    assert params["@dataInicial"] == "'09-01-2026'"
    assert params["@dataFinalCotacao"] == "'09-30-2026'"
    assert params["$select"] == "cotacaoVenda,dataHoraCotacao"


def test_tenta_de_novo_em_erro_5xx_com_espera_exponencial():
    respostas = iter([httpx.Response(502), httpx.Response(503), httpx.Response(200, json=[1])])
    esperas: list[float] = []
    transporte = httpx.MockTransport(lambda _: next(respostas))

    with httpx.Client(transport=transporte) as cliente:
        dados = obter_json(cliente, "https://x.test", {}, tentativas=3, espera=esperas.append)

    assert dados == [1]
    assert esperas == [1, 2]


def test_desiste_apos_as_tentativas():
    transporte = httpx.MockTransport(lambda _: httpx.Response(500))

    with httpx.Client(transport=transporte) as cliente, pytest.raises(ErroDeExtracao):
        obter_json(cliente, "https://x.test", {}, tentativas=2, espera=lambda _: None)


def test_erro_4xx_nao_e_repetido():
    chamadas = []

    def responder(requisicao):
        chamadas.append(requisicao)
        return httpx.Response(400)

    transporte = httpx.MockTransport(responder)

    with httpx.Client(transport=transporte) as cliente, pytest.raises(httpx.HTTPStatusError):
        obter_json(cliente, "https://x.test", {}, tentativas=3, espera=lambda _: None)

    assert len(chamadas) == 1


def test_resposta_do_ibge_em_formato_inesperado(fontes):
    transporte = httpx.MockTransport(lambda _: httpx.Response(200, json=[]))

    with httpx.Client(transport=transporte) as cliente, pytest.raises(ErroDeExtracao):
        extrair(cliente, AgregadoIbge(1737, 63), date(2025, 1, 1), date(2025, 2, 1))
