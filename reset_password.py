"""Restablece la contraseña de un usuario desde la línea de comandos.

Uso:
    python3 reset_password.py <username_o_email> [--password NUEVA] [--by USERNAME]

Sin --password genera una aleatoria y la imprime una sola vez.
"""
import argparse
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.usuario import Usuario

MIN_PASSWORD_LEN = 6


class AmbiguoError(ValueError):
    """El identificador coincide con el username de un usuario y el email de
    otro: resetear a ciegas iría a la cuenta equivocada."""


def find_user(ident):
    por_username = Usuario.query.filter_by(username=ident).first()
    por_email = Usuario.query.filter_by(email=ident).first()
    if (por_username is not None and por_email is not None
            and por_username.id != por_email.id):
        raise AmbiguoError(
            f'{ident!r} es username de un usuario y email de otro; use el '
            f'username exacto de la cuenta buscada')
    return por_username or por_email


def reset_password(ident, password=None, by=None):
    """Cambia la contraseña y registra auditoría.

    Devuelve (usuario, contraseña_nueva).
    Lanza LookupError si el usuario (o --by) no existe,
    ValueError si la contraseña es demasiado corta.
    """
    user = find_user(ident)
    if user is None:
        raise LookupError(ident)
    if password is not None and len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f'mínimo {MIN_PASSWORD_LEN} caracteres')

    actor = user
    if by is not None:
        actor = find_user(by)
        if actor is None:
            raise LookupError(by)

    new_password = password or secrets.token_urlsafe(16)
    user.set_password(new_password)
    db.session.add(AuditLog(
        user_id=actor.id,
        accion='UPDATE',
        tabla='usuarios',
        registro_id=user.id,
        datos_anteriores=None,
        datos_nuevos={'username': user.username, 'password_hash': '***'},
        ip_address='cli',
    ))
    db.session.commit()
    return user, new_password


def build_parser():
    parser = argparse.ArgumentParser(
        description='Restablece la contraseña de un usuario.')
    parser.add_argument('usuario', help='username o email del usuario')
    parser.add_argument('--password', help='nueva contraseña (si se omite se genera aleatoria)')
    parser.add_argument('--by', help='username que registra la acción en auditoría (default: el propio usuario)')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    app = create_app()
    with app.app_context():
        try:
            user, new_password = reset_password(args.usuario, args.password, args.by)
        except AmbiguoError as exc:
            print(f'Identificador ambiguo: {exc}', file=sys.stderr)
            return 1
        except LookupError as exc:
            print(f'Usuario no encontrado: {exc.args[0]}', file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f'Contraseña inválida: {exc}', file=sys.stderr)
            return 1
        if not user.activo:
            print(f'Advertencia: {user.username} está inactivo.')
        print(f'Contraseña restablecida para {user.username} ({user.email}).')
        if args.password is None:
            print(f'Nueva contraseña: {new_password}')
            print('GUARDE esta contraseña: no se volverá a mostrar.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
