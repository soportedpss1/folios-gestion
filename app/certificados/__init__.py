from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models.tipo_certificado import TipoCertificado
from app.certificados.forms import TipoCertificadoForm
from app.services.audit import log_audit
from app.services.mensajes import DUP_TIPO_CERT
from app.services.queries import get_or_404
from app.decorators import permiso_requerido

certificados_bp = Blueprint('certificados', __name__, url_prefix='/certificados')


@certificados_bp.route('/')
@login_required
@permiso_requerido('certificados.gestionar')
def index():
    certificados = TipoCertificado.query.order_by(TipoCertificado.name).all()
    return render_template('certificados/index.html', certificados=certificados)


@certificados_bp.route('/create', methods=['GET', 'POST'])
@login_required
@permiso_requerido('certificados.gestionar')
def create():
    form = TipoCertificadoForm()
    if form.validate_on_submit():
        if TipoCertificado.query.filter_by(name=form.name.data).first():
            flash(DUP_TIPO_CERT, 'danger')
            return render_template('certificados/create.html', form=form)

        cert = TipoCertificado(name=form.name.data, descripcion=form.descripcion.data, color=form.color.data)
        db.session.add(cert)
        try:
            db.session.flush()
            log_audit(current_user.id, 'INSERT', 'tipo_certificados', cert.id, None, cert.to_dict())
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(DUP_TIPO_CERT, 'danger')
            return render_template('certificados/create.html', form=form)
        flash('Tipo de certificado creado exitosamente.', 'success')
        return redirect(url_for('certificados.index'))
    return render_template('certificados/create.html', form=form)


@certificados_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permiso_requerido('certificados.gestionar')
def edit(id):
    cert = get_or_404(TipoCertificado, id)
    datos_anteriores = cert.to_dict()
    form = TipoCertificadoForm(obj=cert)
    if form.validate_on_submit():
        duplicado = TipoCertificado.query.filter(
            TipoCertificado.name == form.name.data,
            TipoCertificado.id != cert.id,
        ).first()
        if duplicado:
            flash(DUP_TIPO_CERT, 'danger')
            return render_template('certificados/edit.html', form=form, cert=cert)

        cert.name = form.name.data
        cert.descripcion = form.descripcion.data
        cert.color = form.color.data
        try:
            log_audit(current_user.id, 'UPDATE', 'tipo_certificados', cert.id, datos_anteriores, cert.to_dict())
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(DUP_TIPO_CERT, 'danger')
            return render_template('certificados/edit.html', form=form, cert=cert)
        flash('Tipo de certificado actualizado exitosamente.', 'success')
        return redirect(url_for('certificados.index'))
    return render_template('certificados/edit.html', form=form, cert=cert)


@certificados_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@permiso_requerido('certificados.gestionar')
def delete(id):
    cert = get_or_404(TipoCertificado, id)
    datos_anteriores = cert.to_dict()
    cert.activo = False
    log_audit(current_user.id, 'DELETE', 'tipo_certificados', cert.id, datos_anteriores, None)
    db.session.commit()
    flash('Tipo de certificado desactivado exitosamente.', 'success')
    return redirect(url_for('certificados.index'))
