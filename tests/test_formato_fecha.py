"""Formato de fecha dd/mm/aaaa uniforme, independiente del locale.

Los inputs nativos type="date" muestran el formato según el idioma del
navegador; flatpickr con dateFormat d/m/Y fija dd/mm/aaaa siempre. El
servidor acepta dd/mm/aaaa y, como fallback, ISO (marcadores, imports).
"""
from datetime import date

from app.extensions import db
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from app.models.recepcion_folio import RecepcionFolio
from tests.conftest import make_folio


def _centro(nombre):
    c = Centro(name=nombre, telefono='5555555', direccion='Calle 1',
               activo=True)
    db.session.add(c)
    db.session.flush()
    return c


# ------------------------------------------------- assets e inputs flatpickr


def test_base_incluye_assets_flatpickr(auth_client):
    html = auth_client.get('/entregas/').get_data(as_text=True)
    assert 'flatpickr' in html, 'falta el asset flatpickr en base.html'
    assert 'l10n/es' in html, 'falta el locale español de flatpickr'


def test_filtros_fecha_no_usan_input_nativo(auth_client, app, tipo, operador):
    for url in ('/entregas/', '/devoluciones/'):
        html = auth_client.get(url).get_data(as_text=True)
        assert 'type="date"' not in html, (
            f'{url}: el filtro de fecha aún depende del locale del navegador')
        assert 'class="form-control form-control-sm flatpickr"' in html, (
            f'{url}: el filtro de fecha no lleva la clase flatpickr')


def test_formularios_fecha_no_usan_input_nativo(admin_client, tipo):
    for url in ('/recepcion/create', '/entregas/create', '/devoluciones/create'):
        html = admin_client.get(url).get_data(as_text=True)
        assert 'type="date"' not in html, (
            f'{url}: el campo de fecha aún depende del locale del navegador')
        assert 'flatpickr' in html, f'{url}: falta la clase flatpickr'


# --------------------------------------------------------- filtros dd/mm/aaaa


class TestFiltrosFechaLatina:
    """Filtros desde/hasta de Entregas y Devoluciones."""

    def _escenario(self, tipo, operador):
        centro = _centro('Centro A')
        f1 = make_folio(tipo, numero=1000, estado='entregado')
        f2 = make_folio(tipo, numero=2000, estado='entregado')
        db.session.add_all([
            EntregaFolio(folio_id=f1.id, fechaEntrega=date(2026, 3, 1),
                         centroId=centro.id, userId=operador.id),
            EntregaFolio(folio_id=f2.id, fechaEntrega=date(2026, 6, 15),
                         centroId=centro.id, userId=operador.id),
            DevolucionFolio(folio_id=f1.id, fechaDevolucion=date(2026, 3, 10),
                            centroId=centro.id, userId=operador.id),
            DevolucionFolio(folio_id=f2.id, fechaDevolucion=date(2026, 6, 20),
                            centroId=centro.id, userId=operador.id),
        ])
        db.session.commit()

    def test_entregas_rango_fechas_ddmmaa(self, auth_client, app, tipo, operador):
        self._escenario(tipo, operador)
        html = auth_client.get(
            '/entregas/?desde=01/06/2026&hasta=30/06/2026'
        ).get_data(as_text=True)
        assert '>2000<' in html
        assert '>1000<' not in html

    def test_devoluciones_rango_fechas_ddmmaa(self, auth_client, app, tipo, operador):
        self._escenario(tipo, operador)
        html = auth_client.get(
            '/devoluciones/?desde=01/06/2026&hasta=30/06/2026'
        ).get_data(as_text=True)
        assert '>2000<' in html
        assert '>1000<' not in html

    def test_valor_filtro_ddmmaa_visible_en_input(self, auth_client, app, tipo, operador):
        self._escenario(tipo, operador)
        html = auth_client.get('/entregas/?desde=01/06/2026'
                               ).get_data(as_text=True)
        assert 'value="01/06/2026"' in html, (
            'el valor re-renderizado del filtro debe ser dd/mm/aaaa')

    def test_filtro_iso_sigue_aceptandose(self, auth_client, app, tipo, operador):
        self._escenario(tipo, operador)
        html = auth_client.get(
            '/entregas/?desde=2026-06-01&hasta=2026-06-30'
        ).get_data(as_text=True)
        assert '>2000<' in html
        assert '>1000<' not in html


# ------------------------------------------------------------ formularios


class TestFormulariosFechaLatina:
    def test_recepcion_create_acepta_ddmmaa(self, admin_client, tipo):
        resp = admin_client.post('/recepcion/create', data={
            'fecha': '28/09/2026', 'anioCert': 2026, 'tipoCert': tipo.id,
            'folioInicial': 100, 'folioFinal': 105,
        }, follow_redirects=True)
        assert resp.status_code == 200
        recepcion = RecepcionFolio.query.one()
        assert recepcion.fecha == date(2026, 9, 28)

    def test_recepcion_create_iso_sigue_aceptandose(self, admin_client, tipo):
        resp = admin_client.post('/recepcion/create', data={
            'fecha': '2026-09-28', 'anioCert': 2026, 'tipoCert': tipo.id,
            'folioInicial': 100, 'folioFinal': 105,
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert RecepcionFolio.query.one().fecha == date(2026, 9, 28)

    def test_recepcion_fecha_invalida_rechazada(self, admin_client, tipo):
        resp = admin_client.post('/recepcion/create', data={
            'fecha': '99/99/2026', 'anioCert': 2026, 'tipoCert': tipo.id,
            'folioInicial': 100, 'folioFinal': 105,
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert RecepcionFolio.query.count() == 0, (
            'una fecha inválida no debe crear recepción')

    def test_entregas_create_acepta_ddmmaa(
            self, auth_client, app, tipo, centro, operador):
        folio = make_folio(tipo, anio=2026, numero=1500)
        db.session.commit()
        resp = auth_client.post('/entregas/create', data={
            'folio_ids': [folio.id], 'fechaEntrega': '28/09/2026',
            'centroId': centro.id,
        }, follow_redirects=True)
        assert resp.status_code == 200
        entrega = EntregaFolio.query.one()
        assert entrega.fechaEntrega == date(2026, 9, 28)

    def test_devoluciones_create_acepta_ddmmaa(
            self, auth_client, app, folio_entregado, centro, operador):
        resp = auth_client.post('/devoluciones/create', data={
            'folio_ids': [folio_entregado.id], 'fechaDevolucion': '28/09/2026',
            'centroId': centro.id,
        }, follow_redirects=True)
        assert resp.status_code == 200
        devolucion = DevolucionFolio.query.one()
        assert devolucion.fechaDevolucion == date(2026, 9, 28)

    def test_devoluciones_fecha_invalida_rechazada(
            self, auth_client, app, folio_entregado, centro, operador):
        resp = auth_client.post('/devoluciones/create', data={
            'folio_ids': [folio_entregado.id], 'fechaDevolucion': 'no-es-fecha',
            'centroId': centro.id,
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert DevolucionFolio.query.count() == 0, (
            'una fecha inválida no debe crear devolución')
