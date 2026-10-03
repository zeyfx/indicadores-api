from alembic import context

from indicadores import models  # noqa: F401  (registra as tabelas no metadata)
from indicadores.config import configuracao
from indicadores.db import Base, criar_engine

config = context.config
url = config.get_main_option("sqlalchemy.url") or configuracao().database_url


def executar_offline() -> None:
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def executar_online() -> None:
    with criar_engine(url).connect() as conexao:
        context.configure(
            connection=conexao,
            target_metadata=Base.metadata,
            render_as_batch=conexao.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    executar_offline()
else:
    executar_online()
