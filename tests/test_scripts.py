"""Trampas de texto para los scripts de DB (no se pueden ejecutar en CI:
dependen de docker compose con el contenedor db levantado)."""

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'


def test_restore_db_valida_el_gzip_antes_de_restaurar():
    texto = (SCRIPTS / 'restore_db.sh').read_text(encoding='utf-8')
    assert 'gzip -t' in texto, \
        'sin gzip -t, un dump corrupto restaura vacío y dice "completada"'


def test_restore_db_no_usa_process_substitution():
    texto = (SCRIPTS / 'restore_db.sh').read_text(encoding='utf-8')
    assert '< <(' not in texto, \
        'la process substitution oculta el exit status del decompressor'


def test_dump_db_borra_el_dump_parcial_si_falla():
    texto = (SCRIPTS / 'dump_db.sh').read_text(encoding='utf-8')
    assert 'trap' in texto, \
        'un dump fallido debe borrar el .sql.gz truncado que dejó'
