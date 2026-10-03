"""Tabelas iniciais: séries, observações e execuções do ETL

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("codigo", sa.String(50), primary_key=True),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("unidade", sa.String(50), nullable=False),
        sa.Column("frequencia", sa.String(20), nullable=False),
        sa.Column("fonte", sa.String(100), nullable=False),
    )
    op.create_table(
        "observacoes",
        sa.Column(
            "serie_codigo",
            sa.String(50),
            sa.ForeignKey("series.codigo", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("data", sa.Date, primary_key=True),
        sa.Column("valor", sa.Float, nullable=False),
        sa.Column("carregado_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "execucoes_etl",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("serie_codigo", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalizada_em", sa.DateTime(timezone=True)),
        sa.Column("desde", sa.Date),
        sa.Column("extraidas", sa.Integer, nullable=False),
        sa.Column("descartadas", sa.Integer, nullable=False),
        sa.Column("inseridas", sa.Integer, nullable=False),
        sa.Column("atualizadas", sa.Integer, nullable=False),
        sa.Column("erro", sa.Text),
    )
    op.create_index("ix_execucoes_serie_inicio", "execucoes_etl", ["serie_codigo", "iniciada_em"])


def downgrade() -> None:
    op.drop_index("ix_execucoes_serie_inicio", table_name="execucoes_etl")
    op.drop_table("execucoes_etl")
    op.drop_table("observacoes")
    op.drop_table("series")
