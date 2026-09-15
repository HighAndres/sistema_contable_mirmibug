"""cfdi clasificacion manual (deducible / concepto / cuenta contable)

Revision ID: b2d5f8a1c604
Revises: f3c1a9d2e7b4
Create Date: 2026-09-15 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2d5f8a1c604'
down_revision: Union[str, None] = 'f3c1a9d2e7b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cfdis', sa.Column('clasificacion', sa.String(length=20), nullable=True))
    op.add_column('cfdis', sa.Column('concepto', sa.String(length=60), nullable=True))
    op.add_column('cfdis', sa.Column('cuenta_contable', sa.String(length=20), nullable=True))
    op.add_column('cfdis', sa.Column('referencia_bancaria', sa.String(length=40), nullable=True))
    op.create_index(op.f('ix_cfdis_clasificacion'), 'cfdis', ['clasificacion'], unique=False)
    op.create_index(op.f('ix_cfdis_concepto'), 'cfdis', ['concepto'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cfdis_concepto'), table_name='cfdis')
    op.drop_index(op.f('ix_cfdis_clasificacion'), table_name='cfdis')
    op.drop_column('cfdis', 'referencia_bancaria')
    op.drop_column('cfdis', 'cuenta_contable')
    op.drop_column('cfdis', 'concepto')
    op.drop_column('cfdis', 'clasificacion')
