"""indices compuestos de consulta

Revision ID: 0003_indexes
Revises: 0002_integrity
Create Date: 2026-09-28 21:31:01.802138

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0003_indexes'
down_revision = '0002_integrity'
branch_labels = None
depends_on = None


def upgrade():
    # Crear primero los índices nuevos: idx_folio_tipoCert_id no se puede dropear
    # hasta que el compuesto idx_folios_tipo_anio cubra el FK (error 1553).
    # IF NOT EXISTS: algunas bases (creadas fuera de esta cadena de migraciones)
    # ya traen idx_audit_fecha y el CREATE fallaría con "Duplicate key name".
    op.get_bind().execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_audit_fecha ON audit_logs (fecha)"
    ))

    with op.batch_alter_table('folios', schema=None) as batch_op:
        batch_op.create_index('idx_folios_anio_estado', ['anioCert', 'estado', 'nulo'], unique=False)
        batch_op.create_index('idx_folios_tipo_anio', ['tipoCert_id', 'anioCert'], unique=False)
        batch_op.drop_index(batch_op.f('idx_folio_anioCert'))
        batch_op.drop_index(batch_op.f('idx_folio_digitado'))
        batch_op.drop_index(batch_op.f('idx_folio_escaneado'))
        batch_op.drop_index(batch_op.f('idx_folio_nulo'))
        batch_op.drop_index(batch_op.f('idx_folio_tipoCert_id'))

    # ### end Alembic commands ###


def downgrade():
    # Orden inverso: recrear los índices simples (el FK necesita uno en tipoCert_id)
    # antes de dropear los compuestos.
    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_index('idx_audit_fecha')

    with op.batch_alter_table('folios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('idx_folio_anioCert'), ['anioCert'], unique=False)
        batch_op.create_index(batch_op.f('idx_folio_digitado'), ['digitado'], unique=False)
        batch_op.create_index(batch_op.f('idx_folio_escaneado'), ['escaneado'], unique=False)
        batch_op.create_index(batch_op.f('idx_folio_nulo'), ['nulo'], unique=False)
        batch_op.create_index(batch_op.f('idx_folio_tipoCert_id'), ['tipoCert_id'], unique=False)
        batch_op.drop_index('idx_folios_tipo_anio')
        batch_op.drop_index('idx_folios_anio_estado')

    # ### end Alembic commands ###
