from urllib.parse import urlparse


def _login_post(client, next_param):
    return client.post(
        f'/auth/login?next={next_param}',
        data={'username': 'operador', 'password': 'pass12345'},
    )


def test_login_next_externo_no_redirige_fuera_del_sitio(client, app, operador):
    """next apuntando a otro dominio debe ignorarse (open redirect)."""
    resp = _login_post(client, 'https://evil.example.com/phish')
    assert resp.status_code == 302
    location = resp.headers['Location']
    assert urlparse(location).netloc in ('', 'localhost'), (
        f'redirige fuera del sitio: {location}'
    )


def test_login_next_relativo_protocolo_invalido_no_redirige_fuera(client, app, operador):
    """next con URL relativa de protocolo (//evil.com) también debe ignorarse."""
    resp = _login_post(client, '//evil.example.com')
    assert resp.status_code == 302
    location = resp.headers['Location']
    assert urlparse(location).netloc in ('', 'localhost'), (
        f'redirige fuera del sitio: {location}'
    )


def test_login_next_relativo_interno_si_se_respeta(client, app, operador):
    resp = _login_post(client, '/folios/')
    assert resp.status_code == 302
    assert resp.headers['Location'] == '/folios/'
