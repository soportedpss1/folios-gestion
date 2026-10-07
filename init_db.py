import sys
import os
import secrets
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models.usuario import Usuario
from app.models.tipo_certificado import TipoCertificado


def init_database():
    app = create_app()
    with app.app_context():
        print("Creando tablas...")
        db.create_all()

        admin_password = None
        if not Usuario.query.filter_by(username='admin').first():
            print("Creando usuario admin...")
            admin_password = secrets.token_urlsafe(16)
            admin = Usuario(
                name='Administrador',
                username='admin',
                email='admin@salud.gob.cu',
                rol='admin',
                activo=True
            )
            admin.set_password(admin_password)
            db.session.add(admin)

        tipos_cert = [
            'Nacimientos Nacionales',
            'Nacimientos Extranjeros',
            'Defunciones',
            'Defunciones Fetales'
        ]

        for nombre in tipos_cert:
            if not TipoCertificado.query.filter_by(name=nombre).first():
                print(f"Creando tipo de certificado: {nombre}")
                cert = TipoCertificado(name=nombre, color='#0D6EFD', activo=True)
                db.session.add(cert)

        db.session.commit()
        print("Base de datos inicializada correctamente.")
        if admin_password:
            print(f"Usuario admin creado: admin / {admin_password}")
            print("GUARDE esta contraseña: no se volverá a mostrar.")


if __name__ == '__main__':
    init_database()
