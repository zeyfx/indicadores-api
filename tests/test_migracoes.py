from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from indicadores.db import Base

RAIZ = Path(__file__).resolve().parents[1]


def test_migracoes_correspondem_aos_modelos(tmp_path):
    url = f"sqlite:///{tmp_path / 'migracao.db'}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")

    engine = create_engine(url)
    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    engine.dispose()
    assert diferencas == []

    command.downgrade(cfg, "base")
