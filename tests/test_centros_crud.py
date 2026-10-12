"""CRUD de centros: unicidad de nombre y reactivación de inactivos."""

from app.extensions import db
from app.models.centro import Centro


def test_create_centro_duplicado_rechazado(admin_client, centro):
    """La unicidad de nombre solo se validaba al importar: create/edit
    permitían duplicados idénticos en todos los selects y exports."""
    resp = admin_client.post('/centros/create', follow_redirects=True, data={
        'name': centro.name, 'telefono': '555', 'direccion': 'Calle 1',
    })
    assert resp.status_code == 200
    assert Centro.query.filter_by(name=centro.name).count() == 1, \
        'no debe crear un centro con nombre duplicado'


def test_edit_centro_nombre_duplicado_rechazado(admin_client, centro, app):
    otro = Centro(name='Otro Centro', telefono='1', direccion='d', activo=True)
    db.session.add(otro)
    db.session.commit()

    resp = admin_client.post(f'/centros/{otro.id}/edit', follow_redirects=True,
                             data={'name': centro.name, 'telefono': '2',
                                   'direccion': 'x'})
    assert resp.status_code == 200
    db.session.refresh(otro)
    assert otro.name == 'Otro Centro', 'no debe renombrar a nombre duplicado'


def test_desactivar_y_reactivar_centro(admin_client, app):
    """Desactivar era irreversible: ningún formulario permitía volver a
    poner activo=True, y el nombre quedaba bloqueado de re-importar."""
    centro = Centro(name='Reactivable', telefono='5', direccion='d', activo=True)
    db.session.add(centro)
    db.session.commit()

    admin_client.post(f'/centros/{centro.id}/delete', follow_redirects=True)
    db.session.refresh(centro)
    assert not centro.activo, 'delete debe desactivar'

    resp = admin_client.post(f'/centros/{centro.id}/edit', follow_redirects=True,
                             data={'name': 'Reactivable', 'telefono': '5',
                                   'direccion': 'd', 'activo': 'y'})
    assert resp.status_code == 200
    db.session.refresh(centro)
    assert centro.activo, 'edit debe poder reactivar el centro'


def test_desactivar_y_reactivar_tipo_certificado(admin_client, app):
    from app.models.tipo_certificado import TipoCertificado
    cert = TipoCertificado(name='Reactivable', color='#0D6EFD', activo=True)
    db.session.add(cert)
    db.session.commit()

    admin_client.post(f'/certificados/{cert.id}/delete', follow_redirects=True)
    db.session.refresh(cert)
    assert not cert.activo

    resp = admin_client.post(f'/certificados/{cert.id}/edit',
                             follow_redirects=True,
                             data={'name': 'Reactivable', 'descripcion': '',
                                   'color': '#0D6EFD', 'activo': 'y'})
    assert resp.status_code == 200
    db.session.refresh(cert)
    assert cert.activo, 'edit debe poder reactivar el tipo de certificado'


def test_export_centro_nombre_con_saltos_no_da_500(admin_client, app):
    """El nombre va crudo al header Content-Disposition: un '\\n' hacía que
    werkzeug tirara ValueError → 500 del export para todos."""
    centro = Centro(name='Centro "Raro"\nOtro', telefono='1', direccion='d',
                    activo=True)
    db.session.add(centro)
    db.session.commit()

    resp = admin_client.get(f'/centros/{centro.id}/export/excel')
    assert resp.status_code == 200, 'el nombre del centro no debe romper el export'
