from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from indicadores.config import configuracao


class Base(DeclarativeBase):
    pass


def ativar_chaves_estrangeiras(engine: Engine) -> Engine:
    """O SQLite ignora chaves estrangeiras por padrão; liga para se comportar como o PostgreSQL."""
    if engine.dialect.name == "sqlite":
        event.listen(
            engine, "connect", lambda conexao, _: conexao.execute("PRAGMA foreign_keys=ON")
        )
    return engine


def criar_engine(url: str) -> Engine:
    argumentos = {}
    if url.startswith("sqlite"):
        argumentos["connect_args"] = {"check_same_thread": False}
    return ativar_chaves_estrangeiras(create_engine(url, pool_pre_ping=True, **argumentos))


@lru_cache
def fabrica_padrao() -> sessionmaker[Session]:
    return sessionmaker(criar_engine(configuracao().database_url), expire_on_commit=False)


def obter_fabrica() -> sessionmaker[Session]:
    """Dependência da API; os testes a substituem por um banco próprio."""
    return fabrica_padrao()


def abrir_sessao(fabrica: sessionmaker[Session]) -> Iterator[Session]:
    with fabrica() as sessao:
        yield sessao
