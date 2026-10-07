"""Encabezado compartido de los PDF exportados (WeasyPrint).

El logo va como data-URI: WeasyPrint lo incrusta sin acceder a la red ni al
sistema de archivos. Sin logo el encabezado queda solo con los textos.
"""

from base64 import b64encode

from app.models.marca import get_marca


def logo_pdf():
    """`<img>` centrado con el logo actual, o '' si no hay logo."""
    try:
        cfg = get_marca()
    except Exception:
        return ''
    if not cfg.logo:
        return ''
    b64 = b64encode(cfg.logo).decode('ascii')
    mime = cfg.logo_mime or 'image/png'
    return (
        f'<img src="data:{mime};base64,{b64}" alt="" '
        'style="display:block; height:48px; margin:0 auto 8px;">'
    )


def encabezado_pdf(titulo):
    """Bloque `.header` completo: logo opcional + textos institucionales + h3."""
    return f'''
        <div class="header">
            {logo_pdf()}
            <h1>Direccion Provincial de Salud Santiago 1</h1>
            <h2>Departamento de Bioestadistica</h2>
            <h3>{titulo}</h3>
        </div>'''
