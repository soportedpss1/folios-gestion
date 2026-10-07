from datetime import timedelta

from app.extensions import db
from app.utils import utcnow

# Reintentos tras un fallo (min). El worker reintenta antes de esperar la
# frecuencia completa, pero sin martillar la API de Google en cada tick.
RETRASO_REINTENTO_FALLA_MIN = 15

FRECUENCIA_MIN_MINUTOS = 5
FRECUENCIA_MAX_MINUTOS = 10080  # 7 días
FRECUENCIA_DEFECTO_MINUTOS = 60


class SyncConfig(db.Model):
    """Fila singleton (id=1) con el estado y la frecuencia del sync a Sheets."""

    __tablename__ = 'sync_config'

    id = db.Column(db.Integer, primary_key=True)
    activo = db.Column(db.Boolean, nullable=False, default=False)
    frecuencia_minutos = db.Column(db.Integer, nullable=False, default=FRECUENCIA_DEFECTO_MINUTOS)
    ultimo_sync_at = db.Column(db.DateTime)          # último éxito
    ultimo_intento_at = db.Column(db.DateTime)       # último intento (éxito o fallo)
    ultimo_resultado = db.Column(db.String(255))     # "12 agregadas, 3 actualizadas..."
    ultimo_error = db.Column(db.Text)                # vacío = último intento OK
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f'<SyncConfig activo={self.activo} {self.frecuencia_minutos}min>'

    def to_dict(self):
        return {
            'id': self.id,
            'activo': self.activo,
            'frecuencia_minutos': self.frecuencia_minutos,
            'ultimo_sync_at': self.ultimo_sync_at,
            'ultimo_intento_at': self.ultimo_intento_at,
            'ultimo_resultado': self.ultimo_resultado,
            'ultimo_error': self.ultimo_error,
            'updated_at': self.updated_at,
        }


def get_config():
    """Devuelve la fila singleton, creándola con valores por defecto si falta."""
    cfg = db.session.get(SyncConfig, 1)
    if cfg is None:
        cfg = SyncConfig(id=1)
        db.session.add(cfg)
        db.session.commit()
    return cfg


def retraso_minutos(cfg):
    """Minutos hasta el próximo intento: tras un fallo se reintenta antes."""
    if cfg.ultimo_error:
        return RETRASO_REINTENTO_FALLA_MIN
    return cfg.frecuencia_minutos


def debe_ejecutar(cfg, ahora):
    """True si al worker le toca sincronizar en `ahora` (UTC naive)."""
    if not cfg.activo:
        return False
    if cfg.ultimo_intento_at is None:
        return True
    return ahora >= cfg.ultimo_intento_at + timedelta(minutes=retraso_minutos(cfg))


def proximo_intento(cfg, ahora):
    """Momento (UTC naive) del próximo intento según la config actual.

    - Desactivado → None.
    - Activo sin intentos previos → None (inmediato: al iniciar el worker).
    - Si el próximo ya pasó, devuelve ese instance (atrasado: pendiente)."""
    if not cfg.activo or cfg.ultimo_intento_at is None:
        return None
    return cfg.ultimo_intento_at + timedelta(minutes=retraso_minutos(cfg))


def registrar_intento(cfg, counts=None, error=None):
    """Estado compartido del sync: manual, worker y API dejan el resultado aquí.

    `counts` = dict de sincronizar() en éxito; `error` = mensaje en español en fallo."""
    ahora = utcnow()
    cfg.ultimo_intento_at = ahora
    if error is None:
        cfg.ultimo_sync_at = ahora
        cfg.ultimo_resultado = (
            f"{counts['agregadas']} agregadas, {counts['actualizadas']} actualizadas, "
            f"{counts['eliminadas']} eliminadas (total {counts['total']})"
        )
        cfg.ultimo_error = None
    else:
        cfg.ultimo_error = error[:2000]
    db.session.commit()
    return cfg
