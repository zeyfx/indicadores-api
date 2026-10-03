from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from indicadores.db import Base


class Serie(Base):
    __tablename__ = "series"

    codigo: Mapped[str] = mapped_column(String(50), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    unidade: Mapped[str] = mapped_column(String(50))
    frequencia: Mapped[str] = mapped_column(String(20))
    fonte: Mapped[str] = mapped_column(String(100))


class Observacao(Base):
    __tablename__ = "observacoes"

    serie_codigo: Mapped[str] = mapped_column(
        ForeignKey("series.codigo", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[date] = mapped_column(Date, primary_key=True)
    valor: Mapped[float] = mapped_column(Float)
    carregado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExecucaoEtl(Base):
    __tablename__ = "execucoes_etl"
    __table_args__ = (Index("ix_execucoes_serie_inicio", "serie_codigo", "iniciada_em"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    serie_codigo: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    iniciada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finalizada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    desde: Mapped[date | None] = mapped_column(Date)
    extraidas: Mapped[int] = mapped_column(Integer, default=0)
    descartadas: Mapped[int] = mapped_column(Integer, default=0)
    inseridas: Mapped[int] = mapped_column(Integer, default=0)
    atualizadas: Mapped[int] = mapped_column(Integer, default=0)
    erro: Mapped[str | None] = mapped_column(Text)
