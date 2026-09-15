"""cfdi: campos del comprobante que piden los reportes del contador

Revision ID: c7e4b0a9d213
Revises: b2d5f8a1c604
Create Date: 2026-09-15 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e4b0a9d213'
down_revision: Union[str, None] = 'b2d5f8a1c604'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNAS = [
    ('moneda', sa.String(length=3)),
    ('tipo_cambio', sa.Numeric(14, 6)),
    ('regimen_emisor', sa.String(length=5)),
    ('regimen_receptor', sa.String(length=5)),
    ('lugar_expedicion', sa.String(length=10)),
    ('domicilio_receptor', sa.String(length=10)),
    ('exportacion', sa.String(length=10)),
    ('condiciones_pago', sa.String(length=80)),
]


def upgrade() -> None:
    for nombre, tipo in COLUMNAS:
        op.add_column('cfdis', sa.Column(nombre, tipo, nullable=True))
    op.add_column('cfdis', sa.Column('descuento', sa.Numeric(14, 2), nullable=False, server_default='0'))
    op.add_column('cfdi_conceptos', sa.Column('clave_prodserv', sa.String(length=15), nullable=True))


def downgrade() -> None:
    op.drop_column('cfdi_conceptos', 'clave_prodserv')
    op.drop_column('cfdis', 'descuento')
    for nombre, _ in reversed(COLUMNAS):
        op.drop_column('cfdis', nombre)
