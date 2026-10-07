"""marca visible de la aplicación (nombre, subtítulo, logo y favicon BLOB)

Revision ID: 0006_marca_config
Revises: 0005_permisos_usuario
Create Date: 2026-10-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = '0006_marca_config'
down_revision = '0005_permisos_usuario'
branch_labels = None
depends_on = None

# BLOB (64 KB) no alcanza para los 512 KB permitidos por imagen.
_IMAGEN = sa.LargeBinary().with_variant(mysql.LONGBLOB(), 'mysql')


def upgrade():
    op.create_table(
        'marca_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=50), nullable=False),
        sa.Column('titulo_sufijo', sa.String(length=50), nullable=True),
        sa.Column('subtitulo', sa.String(length=80), nullable=True),
        sa.Column('logo', _IMAGEN, nullable=True),
        sa.Column('logo_mime', sa.String(length=50), nullable=True),
        sa.Column('favicon', _IMAGEN, nullable=True),
        sa.Column('favicon_mime', sa.String(length=50), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('marca_config')
