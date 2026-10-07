"""Vacía todas las tablas de la base de datos excepto `usuarios`.

Uso:
    python3 vaciar_tablas.py [--by USERNAME]

Muestra el conteo de filas, advierte que la acción es irreversible y pide
doble confirmación: responder 's' y luego escribir BORRAR (exacto).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError

from app import create_app
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.usuario import Usuario
from app.services.backup import TABLAS_ORDEN, estadisticas

TABLAS_A_VACIAR = tuple(n for n in TABLAS_ORDEN if n != 'usuarios')

PALABRA_SECRETA = 'BORRAR'


def _resolver_actor(ident):
    """Usuario que queda registrado en auditoría.

    Si `ident` es None: el primer admin activo, si no el primer usuario.
    Lanza LookupError si `ident` no existe. Devuelve None si no hay usuarios.
    """
    if ident is not None:
        user = (Usuario.query.filter_by(username=ident).first()
                or Usuario.query.filter_by(email=ident).first())
        if user is None:
            raise LookupError(ident)
        return user
    return (Usuario.query.filter_by(rol='admin', activo=True)
            .order_by(Usuario.id).first()
            or Usuario.query.order_by(Usuario.id).first())


def vaciar(by=None):
    """Borra todas las tablas menos `usuarios`. Devuelve {tabla: filas borradas}.

    Lanza LookupError si `by` no existe (no se toca nada) o SQLAlchemyError
    si falla la DB (rollback: queda como estaba).
    """
    actor = _resolver_actor(by)
    filas = {nombre: estadisticas()[nombre] for nombre in TABLAS_A_VACIAR}
    try:
        # Orden inverso: hijos primero, sin necesidad de FOREIGN_KEY_CHECKS.
        for nombre in reversed(TABLAS_A_VACIAR):
            db.session.execute(delete(db.metadata.tables[nombre]))
        if actor is not None:
            db.session.add(AuditLog(
                user_id=actor.id,
                accion='DELETE',
                tabla='*',
                registro_id=0,
                datos_anteriores=None,
                datos_nuevos={'tablas': list(TABLAS_A_VACIAR), 'filas': filas},
                ip_address='cli',
            ))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return filas


def imprimir_advertencia(stats):
    print('ADVERTENCIA: esta acción es IRREVERSIBLE.')
    print(f'Se vaciarán {len(TABLAS_A_VACIAR)} tablas; se conserva SOLO '
          'la tabla usuarios.')
    print('Recomendación: cree una copia de respaldo antes (módulo /backup).')
    print()
    print('Filas a borrar:')
    for nombre in TABLAS_A_VACIAR:
        print(f'  {nombre:<20} {stats[nombre]}')
    print('Filas conservadas:')
    print(f'  {"usuarios":<20} {stats["usuarios"]}')
    print()


def confirmar():
    """Doble confirmación: 's' y luego BORRAR exacto. False si duda o EOF."""
    try:
        if input('¿Continuar? [s/N]: ').strip().lower() not in ('s', 'si', 'sí'):
            return False
        return input(f'Escribe {PALABRA_SECRETA} para confirmar: ').strip() == PALABRA_SECRETA
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def build_parser():
    parser = argparse.ArgumentParser(
        description='Vacía todas las tablas excepto usuarios.')
    parser.add_argument('--by',
                        help='username/email que registra la acción en auditoría '
                             '(default: el primer admin activo)')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    app = create_app()
    with app.app_context():
        stats = estadisticas()
        imprimir_advertencia(stats)
        if not confirmar():
            print('Operación cancelada: no se modificó nada.', file=sys.stderr)
            return 1
        try:
            borradas = vaciar(args.by)
        except LookupError as exc:
            print(f'Usuario no encontrado: {exc.args[0]}', file=sys.stderr)
            return 1
        except SQLAlchemyError as exc:
            print(f'Error al vaciar las tablas (no se modificó nada): {exc}',
                  file=sys.stderr)
            return 1
        total = sum(borradas.values())
        print(f'Listo: {total} filas borradas en {len(TABLAS_A_VACIAR)} tablas. '
              f'usuarios intacta ({stats["usuarios"]} filas).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
