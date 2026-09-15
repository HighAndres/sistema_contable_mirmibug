"""conciliacion: ligas N:M movimiento-CFDI (1:N y N:1) y estado parcial

Revision ID: f3c1a9d2e7b4
Revises: e1a7c2d9f4b0
Create Date: 2026-09-07 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3c1a9d2e7b4'
down_revision: Union[str, None] = 'e1a7c2d9f4b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'conciliacion_ligas',
        sa.Column('movimiento_id', sa.Uuid(), nullable=False),
        sa.Column('cfdi_id', sa.Uuid(), nullable=False),
        sa.Column('importe', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['cfdi_id'], ['cfdis.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['movimiento_id'], ['movimientos_bancarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('movimiento_id', 'cfdi_id', name='uq_liga_movimiento_cfdi'),
    )
    op.create_index(op.f('ix_conciliacion_ligas_cfdi_id'), 'conciliacion_ligas', ['cfdi_id'], unique=False)
    op.create_index(op.f('ix_conciliacion_ligas_movimiento_id'), 'conciliacion_ligas', ['movimiento_id'], unique=False)

    # Lo ya conciliado 1:1 se conserva como una liga por el monto completo del movimiento.
    op.execute(
        """
        INSERT INTO conciliacion_ligas (id, movimiento_id, cfdi_id, importe, created_at, updated_at)
        SELECT gen_random_uuid(), m.id, m.cfdi_id, ABS(m.abono - m.cargo), now(), now()
        FROM movimientos_bancarios m
        WHERE m.cfdi_id IS NOT NULL
        """
    )
    op.drop_index(op.f('ix_movimientos_bancarios_cfdi_id'), table_name='movimientos_bancarios')
    op.drop_constraint('movimientos_bancarios_cfdi_id_fkey', 'movimientos_bancarios', type_='foreignkey')
    op.drop_column('movimientos_bancarios', 'cfdi_id')


def downgrade() -> None:
    op.add_column('movimientos_bancarios', sa.Column('cfdi_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('movimientos_bancarios_cfdi_id_fkey', 'movimientos_bancarios', 'cfdis', ['cfdi_id'], ['id'], ondelete='SET NULL')
    op.create_index(op.f('ix_movimientos_bancarios_cfdi_id'), 'movimientos_bancarios', ['cfdi_id'], unique=False)
    # Se conserva solo la primera liga de cada movimiento (el modelo anterior era 1:1).
    op.execute(
        """
        UPDATE movimientos_bancarios m SET cfdi_id = l.cfdi_id
        FROM (
            SELECT DISTINCT ON (movimiento_id) movimiento_id, cfdi_id
            FROM conciliacion_ligas ORDER BY movimiento_id, created_at
        ) l
        WHERE l.movimiento_id = m.id
        """
    )
    op.execute("UPDATE movimientos_bancarios SET estado = 'pendiente' WHERE estado = 'parcial'")
    op.drop_index(op.f('ix_conciliacion_ligas_movimiento_id'), table_name='conciliacion_ligas')
    op.drop_index(op.f('ix_conciliacion_ligas_cfdi_id'), table_name='conciliacion_ligas')
    op.drop_table('conciliacion_ligas')
