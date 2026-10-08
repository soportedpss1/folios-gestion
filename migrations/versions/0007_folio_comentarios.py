"""comentarios en el detalle de folio (historial con autor y fecha)

Revision ID: 0007_folio_comentarios
Revises: 0006_marca_config
Create Date: 2026-10-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0007_folio_comentarios'
down_revision = '0006_marca_config'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'folio_comentarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('folio_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('texto', sa.String(length=1000), nullable=False),
        sa.Column('createAt', sa.DateTime(), nullable=True),
        sa.Column('updateAt', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['folio_id'], ['folios.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_folio_comentarios_folio_id'),
                    'folio_comentarios', ['folio_id'], unique=False)
    op.create_index(op.f('ix_folio_comentarios_user_id'),
                    'folio_comentarios', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_folio_comentarios_user_id'),
                  table_name='folio_comentarios')
    op.drop_index(op.f('ix_folio_comentarios_folio_id'),
                  table_name='folio_comentarios')
    op.drop_table('folio_comentarios')
