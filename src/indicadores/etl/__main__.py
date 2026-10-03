"""Linha de comando do ETL: python -m indicadores.etl [--serie CODIGO ...] [--desde AAAA-MM-DD]"""

import argparse
import logging
import sys
from datetime import date

from indicadores.catalogo import SERIES
from indicadores.db import fabrica_padrao
from indicadores.etl.pipeline import executar_series


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m indicadores.etl", description=__doc__)
    parser.add_argument(
        "--serie",
        action="append",
        choices=sorted(SERIES),
        help="série a carregar (repita para várias; padrão: todas)",
    )
    parser.add_argument(
        "--desde",
        type=date.fromisoformat,
        help="recarrega a partir desta data, ignorando a carga incremental",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    execucoes = executar_series(fabrica_padrao(), args.serie, desde=args.desde)

    print(
        f"\n{'série':<14}{'status':<10}{'desde':<12}{'extraídas':>10}{'inseridas':>10}"
        f"{'atualizadas':>12}{'descartadas':>12}"
    )
    for e in execucoes:
        print(
            f"{e.serie_codigo:<14}{e.status:<10}{e.desde!s:<12}{e.extraidas:>10}"
            f"{e.inseridas:>10}{e.atualizadas:>12}{e.descartadas:>12}"
        )
        if e.erro:
            print(f"  erro: {e.erro}")
    return 1 if any(e.status != "sucesso" for e in execucoes) else 0


if __name__ == "__main__":
    sys.exit(main())
