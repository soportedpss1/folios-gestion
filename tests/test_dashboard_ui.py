"""F4 — dashboard: tarjetas KPI accesibles y responsive, un solo modal parametrizado."""


def test_kpis_accesibles_y_responsive(auth_client):
    html = auth_client.get('/dashboard/').get_data(as_text=True)
    assert html.count('kpi-card') >= 7, 'faltan tarjetas con clase kpi-card'
    assert html.count('role="button"') >= 7, 'KPIs sin role=button (no accesibles)'
    assert html.count('tabindex="0"') >= 7, 'KPIs sin tabindex (no enfocables)'
    assert 'style="cursor:pointer;"' not in html, 'cursor pointer inline en KPIs'
    # Grid responsive: 2 col en móvil, 3 en md, 4 en xl
    assert 'col-6 col-md-4 col-xl' in html, 'grid de KPIs sin breakpoints'


def test_un_solo_modal_parametrizado(auth_client):
    html = auth_client.get('/dashboard/').get_data(as_text=True)
    assert html.count('id="kpiModal"') == 1, 'no hay exactamente un modal kpiModal'
    for viejo in ('totalModal', 'digitadoModal', 'escaneadoModal', 'nuloModal',
                  'disponibleModal', 'entregadoModal', 'devueltoModal'):
        assert f'id="{viejo}"' not in html, f'sigue el modal duplicado {viejo}'
    assert 'aria-labelledby="kpiModalLabel"' in html, 'modal sin aria-labelledby'
    assert 'aria-label="Cerrar"' in html, 'btn-close del modal sin aria-label'


def test_modal_config_en_js(auth_client):
    html = auth_client.get('/dashboard/').get_data(as_text=True)
    assert "const KPIS" in html, 'falta el mapa KPIS de configuración del modal'
    assert "abrirModal('total')" in html, 'KPI total no dispara abrirModal'
