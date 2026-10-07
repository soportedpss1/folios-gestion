"""Fase 4 — índices compuestos de consulta (migración 0003)."""

import sqlalchemy

from app.extensions import db


def _indexes(engine, table):
    return {i['name'] for i in sqlalchemy.inspect(engine).get_indexes(table)}


def test_indices_compuestos_folios(app):
    idx = _indexes(db.engine, 'folios')
    assert 'idx_folios_anio_estado' in idx, f'falta índice (anioCert,estado,nulo): {idx}'
    assert 'idx_folios_tipo_anio' in idx, f'falta índice (tipoCert_id,anioCert): {idx}'


def test_indice_audit_fecha(app):
    idx = _indexes(db.engine, 'audit_logs')
    assert 'idx_audit_fecha' in idx, f'falta índice en audit_logs.fecha: {idx}'


def test_indices_compuestos_reales_en_columnas(app):
    insp = sqlalchemy.inspect(db.engine)
    por_nombre = {i['name']: i for i in insp.get_indexes('folios')}
    assert por_nombre['idx_folios_anio_estado']['column_names'] == ['anioCert', 'estado', 'nulo']
    assert por_nombre['idx_folios_tipo_anio']['column_names'] == ['tipoCert_id', 'anioCert']
