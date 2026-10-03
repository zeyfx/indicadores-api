import json
import os
from collections.abc import Iterator
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from indicadores import models  # noqa: F401
from indicadores.api.main import criar_app
from indicadores.api.rotas import obter_transporte
from indicadores.config import configuracao
from indicadores.db import Base, ativar_chaves_estrangeiras, obter_fabrica


@pytest.fixture(autouse=True)
def ambiente(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ETL_API_KEY", "segredo")
    monkeypatch.setenv("HTTP_TENTATIVAS", "1")
    configuracao.cache_clear()
    yield
    configuracao.cache_clear()


@pytest.fixture
def fabrica() -> Iterator[sessionmaker[Session]]:
    """SQLite em memória por padrão; TEST_DATABASE_URL roda a suíte contra um PostgreSQL."""
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url)
    else:
        engine = ativar_chaves_estrangeiras(
            create_engine(
                "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
            )
        )
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    Base.metadata.drop_all(engine)
    engine.dispose()


class FontesFalsas:
    """Simula as APIs do IBGE e do PTAX e guarda as requisições recebidas."""

    def __init__(self) -> None:
        self.ibge: dict[int, dict[str, str]] = {
            63: {"202501": "0.16", "202502": "1.31", "202503": "0.56"},
            2266: {"202501": "7000.00", "202502": "7091.70", "202503": "7131.41"},
        }
        self.ptax: list[dict] = [
            {"cotacaoVenda": 5.10, "dataHoraCotacao": "2026-09-01 13:06:03.857125"},
            {"cotacaoVenda": 5.12, "dataHoraCotacao": "2026-09-02 13:02:37"},
        ]
        self.falhar: set[str] = set()
        self.requisicoes: list[httpx.Request] = []

    def __call__(self, requisicao: httpx.Request) -> httpx.Response:
        self.requisicoes.append(requisicao)
        host = requisicao.url.host
        if host in self.falhar:
            return httpx.Response(503)
        if host == "servicodados.ibge.gov.br":
            variavel = int(requisicao.url.path.rsplit("/", 1)[-1])
            corpo = [{"resultados": [{"series": [{"serie": self.ibge[variavel]}]}]}]
            return httpx.Response(200, json=corpo)
        if host == "olinda.bcb.gov.br":
            return httpx.Response(200, content=json.dumps({"value": self.ptax}))
        return httpx.Response(404)

    @property
    def transporte(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


@pytest.fixture
def fontes() -> FontesFalsas:
    return FontesFalsas()


@pytest.fixture
def cliente(fabrica, fontes) -> Iterator[TestClient]:
    app = criar_app()
    app.dependency_overrides[obter_fabrica] = lambda: fabrica
    app.dependency_overrides[obter_transporte] = lambda: fontes.transporte
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture
def hoje() -> date:
    return date(2026, 10, 3)
