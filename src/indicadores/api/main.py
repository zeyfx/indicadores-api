from fastapi import FastAPI

from indicadores.api.rotas import rotas


def criar_app() -> FastAPI:
    app = FastAPI(
        title="Indicadores API",
        version="0.1.0",
        description=(
            "Indicadores econômicos (IPCA do IBGE e dólar PTAX do Banco Central) "
            "carregados por um pipeline de ETL incremental."
        ),
    )
    app.include_router(rotas)
    return app


app = criar_app()
