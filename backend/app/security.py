"""Seguridad básica (alcance 2.5.2): contraseñas con PBKDF2 y tokens de sesión firmados (HMAC-SHA256)."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import get_settings

ITERACIONES = 240_000


def hash_password(password: str) -> str:
    sal = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), sal.encode(), ITERACIONES).hex()
    return f"pbkdf2${ITERACIONES}${sal}${h}"


def verificar_password(password: str, guardado: str) -> bool:
    try:
        _, it, sal, h = guardado.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), sal.encode(), int(it)).hex()
        return hmac.compare_digest(calc, h)
    except ValueError:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _firma(datos: str) -> str:
    return _b64(hmac.new(get_settings().secret_key.encode(), datos.encode(), hashlib.sha256).digest())


def crear_token(usuario_id: int) -> str:
    exp = int(time.time()) + get_settings().sesion_horas * 3600
    datos = _b64(json.dumps({"uid": usuario_id, "exp": exp}).encode())
    return f"{datos}.{_firma(datos)}"


def leer_token(token: str) -> int | None:
    try:
        datos, firma = token.split(".")
        if not hmac.compare_digest(firma, _firma(datos)):
            return None
        carga = json.loads(_unb64(datos))
        if carga["exp"] < time.time():
            return None
        return int(carga["uid"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
