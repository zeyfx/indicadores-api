from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SerieSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nome: str
    unidade: str
    frequencia: str
    fonte: str
    total_observacoes: int = 0
    primeira_data: date | None = None
    ultima_data: date | None = None


class ObservacaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data: date
    valor: float


class ResumoSaida(BaseModel):
    serie: str
    observacoes: int
    primeira_data: date | None
    ultima_data: date | None
    primeiro_valor: float | None
    ultimo_valor: float | None
    minimo: float | None
    maximo: float | None
    media: float | None
    variacao_percentual: float | None = Field(
        description="Variação entre o primeiro e o último valor do período. "
        "Nula para séries já expressas em %."
    )


class AgregadoSaida(BaseModel):
    periodo: str
    observacoes: int
    media: float
    minimo: float
    maximo: float


class Ipca12mSaida(BaseModel):
    data: date
    acumulado_12m: float


class ExecucaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    serie_codigo: str
    status: str
    iniciada_em: datetime
    finalizada_em: datetime | None
    desde: date | None
    extraidas: int
    descartadas: int
    inseridas: int
    atualizadas: int
    erro: str | None


class PedidoDeExecucao(BaseModel):
    series: list[str] | None = Field(default=None, description="Padrão: todas as séries.")
    desde: date | None = Field(default=None, description="Ignora a carga incremental.")


class ExecucaoAgendada(BaseModel):
    series: list[str]
    mensagem: str
