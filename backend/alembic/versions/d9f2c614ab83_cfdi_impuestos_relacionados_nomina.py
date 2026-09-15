"""cfdi: impuestos por tasa, relacionados, complementos, global y nomina

Revision ID: d9f2c614ab83
Revises: c7e4b0a9d213
Create Date: 2026-09-15 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9f2c614ab83'
down_revision: Union[str, None] = 'c7e4b0a9d213'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLUMNAS_CFDI = [
    ('pac_rfc', sa.String(length=13)),
    ('cuenta_predial', sa.String(length=150)),
    ('complementos', sa.String(length=255)),
    ('global_periodicidad', sa.String(length=5)),
    ('global_meses', sa.String(length=5)),
    ('global_anio', sa.String(length=4)),
    ('fecha_cancelacion', sa.Date()),
    ('motivo_cancelacion', sa.String(length=5)),
    ('folio_sustitucion', sa.String(length=36)),
]


def upgrade() -> None:
    for nombre, tipo in COLUMNAS_CFDI:
        op.add_column('cfdis', sa.Column(nombre, tipo, nullable=True))

    op.create_table(
        'cfdi_impuestos',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('cfdi_id', sa.Uuid(), nullable=False),
        sa.Column('naturaleza', sa.String(length=10), nullable=False),
        sa.Column('impuesto', sa.String(length=10), nullable=False),
        sa.Column('tipo_factor', sa.String(length=10), nullable=True),
        sa.Column('tasa', sa.Numeric(10, 6), nullable=True),
        sa.Column('base', sa.Numeric(14, 2), nullable=False),
        sa.Column('importe', sa.Numeric(14, 2), nullable=False),
        sa.Column('nombre_local', sa.String(length=60), nullable=True),
        sa.ForeignKeyConstraint(['cfdi_id'], ['cfdis.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cfdi_impuestos_cfdi_id'), 'cfdi_impuestos', ['cfdi_id'], unique=False)

    op.create_table(
        'cfdi_relacionados',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('cfdi_id', sa.Uuid(), nullable=False),
        sa.Column('tipo_relacion', sa.String(length=5), nullable=True),
        sa.Column('uuid_relacionado', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['cfdi_id'], ['cfdis.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cfdi_relacionados_cfdi_id'), 'cfdi_relacionados', ['cfdi_id'], unique=False)
    op.create_index(op.f('ix_cfdi_relacionados_uuid_relacionado'), 'cfdi_relacionados', ['uuid_relacionado'], unique=False)

    op.create_table(
        'cfdi_nominas',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('cfdi_id', sa.Uuid(), nullable=False),
        sa.Column('version', sa.String(length=5), nullable=True),
        sa.Column('tipo_nomina', sa.String(length=5), nullable=True),
        sa.Column('fecha_pago', sa.Date(), nullable=True),
        sa.Column('fecha_inicial_pago', sa.Date(), nullable=True),
        sa.Column('fecha_final_pago', sa.Date(), nullable=True),
        sa.Column('num_dias_pagados', sa.Numeric(10, 3), nullable=True),
        sa.Column('total_percepciones', sa.Numeric(14, 2), nullable=False),
        sa.Column('total_deducciones', sa.Numeric(14, 2), nullable=False),
        sa.Column('total_otros_pagos', sa.Numeric(14, 2), nullable=False),
        sa.Column('registro_patronal', sa.String(length=20), nullable=True),
        sa.Column('curp_emisor', sa.String(length=18), nullable=True),
        sa.Column('curp_receptor', sa.String(length=18), nullable=True),
        sa.Column('num_seguridad_social', sa.String(length=15), nullable=True),
        sa.Column('fecha_inicio_rel_laboral', sa.Date(), nullable=True),
        sa.Column('antiguedad', sa.String(length=15), nullable=True),
        sa.Column('tipo_contrato', sa.String(length=5), nullable=True),
        sa.Column('sindicalizado', sa.String(length=2), nullable=True),
        sa.Column('tipo_jornada', sa.String(length=5), nullable=True),
        sa.Column('tipo_regimen', sa.String(length=5), nullable=True),
        sa.Column('num_empleado', sa.String(length=15), nullable=True),
        sa.Column('departamento', sa.String(length=100), nullable=True),
        sa.Column('puesto', sa.String(length=100), nullable=True),
        sa.Column('riesgo_puesto', sa.String(length=5), nullable=True),
        sa.Column('periodicidad_pago', sa.String(length=5), nullable=True),
        sa.Column('banco', sa.String(length=10), nullable=True),
        sa.Column('cuenta_bancaria', sa.String(length=20), nullable=True),
        sa.Column('salario_base_cot_apor', sa.Numeric(14, 2), nullable=True),
        sa.Column('salario_diario_integrado', sa.Numeric(14, 2), nullable=True),
        sa.Column('clave_ent_fed', sa.String(length=5), nullable=True),
        sa.ForeignKeyConstraint(['cfdi_id'], ['cfdis.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cfdi_id'),
    )
    op.create_index(op.f('ix_cfdi_nominas_cfdi_id'), 'cfdi_nominas', ['cfdi_id'], unique=False)
    op.create_index(op.f('ix_cfdi_nominas_fecha_pago'), 'cfdi_nominas', ['fecha_pago'], unique=False)

    op.create_table(
        'cfdi_nomina_conceptos',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('nomina_id', sa.Uuid(), nullable=False),
        sa.Column('grupo', sa.String(length=12), nullable=False),
        sa.Column('tipo_codigo', sa.String(length=5), nullable=True),
        sa.Column('clave', sa.String(length=15), nullable=True),
        sa.Column('concepto', sa.String(length=255), nullable=False),
        sa.Column('gravado', sa.Numeric(14, 2), nullable=False),
        sa.Column('exento', sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(['nomina_id'], ['cfdi_nominas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cfdi_nomina_conceptos_nomina_id'), 'cfdi_nomina_conceptos', ['nomina_id'], unique=False)


def downgrade() -> None:
    op.drop_table('cfdi_nomina_conceptos')
    op.drop_table('cfdi_nominas')
    op.drop_table('cfdi_relacionados')
    op.drop_table('cfdi_impuestos')
    for nombre, _ in reversed(COLUMNAS_CFDI):
        op.drop_column('cfdis', nombre)
