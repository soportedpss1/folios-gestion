"""tabla sync_config (estado y frecuencia del sync a Google Sheets)

Revision ID: 0004_sync_config
Revises: 0003_indexes
Create Date: 2026-10-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0004_sync_config'
down_revision = '0003_indexes'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sync_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('frecuencia_minutos', sa.Integer(), nullable=False),
        sa.Column('ultimo_sync_at', sa.DateTime(), nullable=True),
        sa.Column('ultimo_intento_at', sa.DateTime(), nullable=True),
        sa.Column('ultimo_resultado', sa.String(length=255), nullable=True),
        sa.Column('ultimo_error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('sync_config')
