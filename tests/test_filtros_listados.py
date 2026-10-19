"""Filtros de búsqueda del listado de Entregas y Devoluciones."""
from datetime import date

import pytest

from app.extensions import db
from app.models.centro import Centro
from app.models.devolucion_folio import DevolucionFolio
from app.models.entrega_folio import EntregaFolio
from tests.conftest import make_folio


def _centro(nombre):
    c = Centro(name=nombre, telefono='5555555', direccion='Calle 1',
               activo=True)
    db.session.add(c)
    db.session.flush()
    return c


@pytest.fixture()
def escenario(app, tipo, operador):
    """Dos entregas y dos devoluciones: folios 1000/2000, centros A/B,
    fechas 2026-03-01 / 2026-06-15 (devoluciones 03-10 / 06-20)."""
    centro_a = _centro('Centro A')
    centro_b = _centro('Centro B')
    f1 = make_folio(tipo, numero=1000, estado='entregado')
    f2 = make_folio(tipo, numero=2000, estado='entregado')
    db.session.add_all([
        EntregaFolio(folio_id=f1.id, fechaEntrega=date(2026, 3, 1),
                     centroId=centro_a.id, userId=operador.id),
        EntregaFolio(folio_id=f2.id, fechaEntrega=date(2026, 6, 15),
                     centroId=centro_b.id, userId=operador.id),
        DevolucionFolio(folio_id=f1.id, fechaDevolucion=date(2026, 3, 10),
                        centroId=centro_a.id, userId=operador.id),
        DevolucionFolio(folio_id=f2.id, fechaDevolucion=date(2026, 6, 20),
                        centroId=centro_b.id, userId=operador.id),
    ])
    db.session.commit()
    return {'centro_a': centro_a, 'centro_b': centro_b}


def _pagina(client, url):
    resp = client.get(url)
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


class TestEntregasFiltros:
    def test_sin_filtros_muestra_todo(self, auth_client, escenario):
        body = _pagina(auth_client, '/entregas/')
        assert '>1000<' in body and '>2000<' in body

    def test_busqueda_por_folio(self, auth_client, escenario):
        body = _pagina(auth_client, '/entregas/?busqueda=100')
        assert '>1000<' in body
        assert '>2000<' not in body

    def test_busqueda_sin_resultados(self, auth_client, escenario):
        body = _pagina(auth_client, '/entregas/?busqueda=9999')
        assert 'No hay entregas registradas' in body

    def test_filtro_por_centro(self, auth_client, escenario):
        body = _pagina(auth_client, f"/entregas/?centroId={escenario['centro_b'].id}")
        assert '>2000<' in body
        assert '>1000<' not in body

    def test_filtro_rango_fechas(self, auth_client, escenario):
        body = _pagina(auth_client, '/entregas/?desde=2026-06-01&hasta=2026-06-30')
        assert '>2000<' in body
        assert '>1000<' not in body

    def test_filtro_fecha_desde_excluye_anteriores(self, auth_client, escenario):
        body = _pagina(auth_client, '/entregas/?desde=2026-04-01')
        assert '>2000<' in body
        assert '>1000<' not in body

    def test_filtros_combinados_sin_resultados(self, auth_client, escenario):
        # Centro A + rango que solo cubre junio + folio 2000: sin resultados.
        body = _pagina(
            auth_client,
            f"/entregas/?centroId={escenario['centro_a'].id}"
            '&desde=2026-06-01&busqueda=2000')
        assert 'No hay entregas registradas' in body

    def test_filtros_combinados_con_resultado(self, auth_client, escenario):
        body = _pagina(
            auth_client,
            f"/entregas/?centroId={escenario['centro_b'].id}"
            '&hasta=2026-06-30&busqueda=2000')
        assert '>2000<' in body
        assert '>1000<' not in body

    def test_fecha_invalida_se_ignora(self, auth_client, escenario):
        body = _pagina(auth_client, '/entregas/?desde=basura')
        assert '>1000<' in body and '>2000<' in body


class TestDevolucionesFiltros:
    def test_busqueda_por_folio(self, auth_client, escenario):
        body = _pagina(auth_client, '/devoluciones/?busqueda=200')
        assert '>2000<' in body
        assert '>1000<' not in body

    def test_filtro_por_centro(self, auth_client, escenario):
        body = _pagina(auth_client, f"/devoluciones/?centroId={escenario['centro_a'].id}")
        assert '>1000<' in body
        assert '>2000<' not in body

    def test_filtro_rango_fechas(self, auth_client, escenario):
        body = _pagina(auth_client, '/devoluciones/?desde=2026-06-01&hasta=2026-06-30')
        assert '>2000<' in body
        assert '>1000<' not in body

    def test_sin_filtros_muestra_todo(self, auth_client, escenario):
        body = _pagina(auth_client, '/devoluciones/')
        assert '>1000<' in body and '>2000<' in body
