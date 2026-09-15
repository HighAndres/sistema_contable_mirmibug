"""cfdi pago manual

Revision ID: e1a7c2d9f4b0
Revises: ace482bddcf0
Create Date: 2026-09-07 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a7c2d9f4b0'
down_revision: Union[str, None] = 'ace482bddcf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cfdis', sa.Column('pago_manual_fecha', sa.Date(), nullable=True))
    op.add_column('cfdis', sa.Column('pago_manual_nota', sa.String(length=255), nullable=True))
    op.add_column('cfdis', sa.Column('pago_manual_usuario_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_cfdis_pago_manual_fecha'), 'cfdis', ['pago_manual_fecha'], unique=False)
    op.create_foreign_key('fk_cfdis_pago_manual_usuario', 'cfdis', 'usuarios', ['pago_manual_usuario_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_cfdis_pago_manual_usuario', 'cfdis', type_='foreignkey')
    op.drop_index(op.f('ix_cfdis_pago_manual_fecha'), table_name='cfdis')
    op.drop_column('cfdis', 'pago_manual_usuario_id')
    op.drop_column('cfdis', 'pago_manual_nota')
    op.drop_column('cfdis', 'pago_manual_fecha')
