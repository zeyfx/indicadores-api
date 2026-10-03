from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./indicadores.db"
    # Sem chave definida, o disparo do ETL pela API fica desligado.
    etl_api_key: str | None = None
    http_timeout: float = 30.0
    http_tentativas: int = 3


@lru_cache
def configuracao() -> Configuracao:
    return Configuracao()
