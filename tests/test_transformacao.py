from datetime import date

import numpy as np
import pandas as pd

from indicadores.catalogo import AgregadoIbge, PtaxBcb
from indicadores.etl.transformacao import transformar, validar


def test_ibge_converte_periodo_e_descarta_simbolos_de_ausencia():
    bruto = {"202501": "0.16", "202502": "...", "202503": "-", "202504": "X", "2025AB": "1.0"}

    tabela, descartadas = transformar(AgregadoIbge(1737, 63), bruto)

    assert tabela.to_dict("records") == [{"data": date(2025, 1, 1), "valor": 0.16}]
    assert descartadas == 4


def test_ptax_mantem_a_ultima_cotacao_do_dia():
    bruto = [
        {"cotacaoVenda": 5.20, "dataHoraCotacao": "2026-09-02 13:00:00"},
        {"cotacaoVenda": 5.10, "dataHoraCotacao": "2026-09-01 13:06:03.857125"},
        {"cotacaoVenda": 5.25, "dataHoraCotacao": "2026-09-02 10:00:00"},
    ]

    tabela, descartadas = transformar(PtaxBcb(), bruto)

    assert tabela.to_dict("records") == [
        {"data": date(2026, 9, 1), "valor": 5.10},
        {"data": date(2026, 9, 2), "valor": 5.20},
    ]
    assert descartadas == 1


def test_ptax_descarta_data_ou_valor_invalidos():
    bruto = [
        {"cotacaoVenda": "abc", "dataHoraCotacao": "2026-09-01 13:00:00"},
        {"cotacaoVenda": 5.0, "dataHoraCotacao": "não é data"},
        {"cotacaoVenda": 5.3, "dataHoraCotacao": "2026-09-03 13:00:00"},
    ]

    tabela, descartadas = transformar(PtaxBcb(), bruto)

    assert tabela["valor"].tolist() == [5.3]
    assert descartadas == 2


def test_validar_remove_infinitos_e_ordena():
    tabela = pd.DataFrame(
        {
            "data": [date(2025, 3, 1), date(2025, 1, 1), date(2025, 2, 1)],
            "valor": [3.0, np.inf, 2.0],
        }
    )

    limpa, descartadas = validar(tabela)

    assert limpa["data"].tolist() == [date(2025, 2, 1), date(2025, 3, 1)]
    assert descartadas == 1


def test_fonte_vazia_gera_tabela_vazia():
    tabela, descartadas = transformar(PtaxBcb(), [])

    assert tabela.empty
    assert descartadas == 0
