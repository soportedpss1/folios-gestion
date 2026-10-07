from flask import Blueprint, render_template
from flask_login import current_user

from app.decorators import permiso_requerido
from app.escaneos.forms import EscaneoForm
from app.extensions import db
from app.models.folio import Folio
from app.services.escaneos import guardar_y_matchear

escaneos_bp = Blueprint('escaneos', __name__, url_prefix='/escaneos')


@escaneos_bp.route('/subir', methods=['GET', 'POST'])
# hacia='dashboard' (default): el blueprint no tiene index a donde redirigir.
@permiso_requerido('escaneos.subir')
def subir():
    form = EscaneoForm()
    # choices ANTES de validar: SelectField valida contra ellas.
    anios = [fila[0] for fila in
             db.session.query(Folio.anioCert).distinct()
             .order_by(Folio.anioCert.desc()).all()]
    form.anio.choices = [(a, str(a)) for a in anios]

    reporte = None
    if form.validate_on_submit():
        reporte = guardar_y_matchear(form.archivos.data, form.anio.data,
                                     current_user.id)
    return render_template('escaneos/subir.html', form=form, anios=anios,
                           reporte=reporte)
