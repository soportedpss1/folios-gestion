"""permisos granulares por usuario (grants que suman al rol)

Revision ID: 0005_permisos_usuario
Revises: 0004_sync_config
Create Date: 2026-10-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0005_permisos_usuario'
down_revision = '0004_sync_config'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'permiso_usuarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('permiso', sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['usuarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'permiso', name='uq_permiso_usuario'),
    )
    op.create_index('idx_permiso_usuario_user', 'permiso_usuarios', ['user_id'])


def downgrade():
    op.drop_index('idx_permiso_usuario_user', table_name='permiso_usuarios')
    op.drop_table('permiso_usuarios')
