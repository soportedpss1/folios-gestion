"""transferencias de folios entre centros (motivo obligatorio y seguimiento)

Revision ID: 0008_transferencias
Revises: 0007_folio_comentarios
Create Date: 2026-10-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0008_transferencias'
down_revision = '0007_folio_comentarios'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'transferencia_folios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('folio_id', sa.Integer(), nullable=False),
        sa.Column('centroOrigenId', sa.Integer(), nullable=False),
        sa.Column('centroDestinoId', sa.Integer(), nullable=False),
        sa.Column('userId', sa.Integer(), nullable=False),
        sa.Column('motivo', sa.String(length=500), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['folio_id'], ['folios.id'], ),
        sa.ForeignKeyConstraint(['centroOrigenId'], ['centros.id'], ),
        sa.ForeignKeyConstraint(['centroDestinoId'], ['centros.id'], ),
        sa.ForeignKeyConstraint(['userId'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_transferencia_folios_folio_id'),
                    'transferencia_folios', ['folio_id'], unique=False)
    op.create_index('idx_transferencia_origen',
                    'transferencia_folios', ['centroOrigenId'], unique=False)
    op.create_index('idx_transferencia_destino',
                    'transferencia_folios', ['centroDestinoId'], unique=False)
    op.create_index('idx_transferencia_userId',
                    'transferencia_folios', ['userId'], unique=False)


def downgrade():
    op.drop_index('idx_transferencia_userId', table_name='transferencia_folios')
    op.drop_index('idx_transferencia_destino', table_name='transferencia_folios')
    op.drop_index('idx_transferencia_origen', table_name='transferencia_folios')
    op.drop_index(op.f('ix_transferencia_folios_folio_id'),
                  table_name='transferencia_folios')
    op.drop_table('transferencia_folios')
