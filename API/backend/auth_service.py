import base64
import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from .config import settings

try:
    import jwt as pyjwt
except ImportError:  # pragma: no cover - optional dependency
    pyjwt = None


USERS_DB_FILE = settings.auth_users_db_file
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PROFILE_ALIASES = {
    "admin": "administrador",
    "administrador": "administrador",
    "administrator": "administrador",
    "medico": "medico",
    "m\u00e9dico": "medico",
    "doctor": "medico",
    "recepcao": "recepcao",
    "recep\u00e7\u00e3o": "recepcao",
    "reception": "recepcao",
    "usuario": "usuario",
    "usu\u00e1rio": "usuario",
    "user": "usuario",
}

PROFILE_REDIRECTS = {
    "administrador": "/admin",
    "medico": "/medico",
    "recepcao": "/recepcao",
    "usuario": "/app",
}

PROFILE_PERMISSIONS = {
    "administrador": {
        "admin:read",
        "admin:write",
        "patients:read",
        "patients:write",
        "consultations:read",
        "consultations:write",
        "chat:use",
        "pdf:upload",
        "audio:transcribe",
        "recommendations:read",
        "profiles:select",
    },
    "medico": {
        "patients:read",
        "patients:write",
        "consultations:read",
        "consultations:write",
        "chat:use",
        "pdf:upload",
        "audio:transcribe",
        "recommendations:read",
        "profiles:select",
    },
    "recepcao": {
        "patients:read",
        "patients:write",
        "consultations:read",
        "consultations:write",
        "profiles:select",
    },
    "usuario": {
        "patients:read",
        "consultations:read",
        "profiles:select",
    },
}


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _fallback_jwt_encode(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_part = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_part = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_part}.{payload_part}.{_base64url_encode(signature)}"


def _fallback_jwt_decode(token: str, secret: str) -> dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split(".")
    except ValueError as exc:
        raise AuthError("Token invalido", 401) from exc

    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    provided = _base64url_decode(signature_part)

    if not hmac.compare_digest(expected, provided):
        raise AuthError("Token invalido", 401)

    header = json.loads(_base64url_decode(header_part))
    if header.get("alg") != "HS256":
        raise AuthError("Token invalido", 401)

    payload = json.loads(_base64url_decode(payload_part))
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and _utcnow().timestamp() > exp:
        raise AuthError("Token expirado", 401)
    return payload


@lru_cache(maxsize=1)
def get_auth_secret() -> str:
    if settings.auth_secret_key:
        return settings.auth_secret_key
    raise AuthError("AUTH_SECRET_KEY nao configurado", 500)


def normalize_email(email: Any) -> str:
    if not isinstance(email, str):
        return ""
    return email.strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(email and EMAIL_RE.match(email))


def normalize_profile(profile: Any) -> str:
    if not isinstance(profile, str):
        return ""
    cleaned = profile.strip().lower()
    return PROFILE_ALIASES.get(cleaned, cleaned)


def normalize_profiles(profiles: list[str] | str | None) -> list[str]:
    if isinstance(profiles, str):
        raw_profiles = [item.strip() for item in profiles.split(",")]
    elif isinstance(profiles, list):
        raw_profiles = profiles
    else:
        raw_profiles = []

    normalized: list[str] = []
    for profile in raw_profiles:
        value = normalize_profile(profile)
        if value in PROFILE_PERMISSIONS and value not in normalized:
            normalized.append(value)
    return normalized


def load_users_database() -> dict[str, Any]:
    bootstrap_users_if_needed()
    if not os.path.exists(USERS_DB_FILE):
        return {"users": []}
    try:
        with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (IOError, json.JSONDecodeError):
        print(f"[AUTH] Nao foi possivel carregar {USERS_DB_FILE}. Usando base vazia.")
        return {"users": []}

    if not isinstance(data, dict) or not isinstance(data.get("users"), list):
        return {"users": []}
    return data


def save_users_database(data: dict[str, Any]) -> None:
    directory = os.path.dirname(USERS_DB_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(USERS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def bootstrap_users_if_needed() -> None:
    if os.path.exists(USERS_DB_FILE):
        return

    email = normalize_email(settings.auth_bootstrap_email)
    password = settings.auth_bootstrap_password
    if not email or not password:
        return

    profiles = normalize_profiles(settings.auth_bootstrap_profiles)
    if not profiles:
        profiles = ["administrador"]

    create_user(email, password, settings.auth_bootstrap_name, profiles)


def create_user(email: str, password: str, name: str, profiles: list[str]) -> dict[str, Any]:
    email = normalize_email(email)
    if not is_valid_email(email):
        raise ValueError("Email invalido")
    if not isinstance(password, str) or not password:
        raise ValueError("Senha obrigatoria")

    normalized_profiles = normalize_profiles(profiles)
    if not normalized_profiles:
        raise ValueError("Perfil invalido")

    data = {"users": []}
    if os.path.exists(USERS_DB_FILE):
        try:
            with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get("users"), list):
                    data = loaded
        except (IOError, json.JSONDecodeError):
            data = {"users": []}

    if any(normalize_email(user.get("email")) == email for user in data["users"]):
        raise ValueError("Usuario ja existe")

    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "name": name or email,
        "password_hash": generate_password_hash(password),
        "profiles": normalized_profiles,
        "active": True,
        "created_at": _utcnow().isoformat(),
    }
    data["users"].append(user)
    save_users_database(data)
    return user


def find_user_by_email(email: str) -> dict[str, Any] | None:
    email = normalize_email(email)
    for user in load_users_database().get("users", []):
        if normalize_email(user.get("email")) == email:
            return user
    return None


def find_user_by_id(user_id: str) -> dict[str, Any] | None:
    for user in load_users_database().get("users", []):
        if user.get("id") == user_id:
            return user
    return None


def sanitize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name"),
    }


def get_profile_details(profile: str) -> dict[str, Any]:
    normalized = normalize_profile(profile)
    permissions = sorted(PROFILE_PERMISSIONS.get(normalized, set()))
    return {
        "name": normalized,
        "permissions": permissions,
        "redirect_to": PROFILE_REDIRECTS.get(normalized, "/app"),
    }


def authenticate_user(email: Any, password: Any) -> dict[str, Any] | None:
    normalized_email = normalize_email(email)
    if not is_valid_email(normalized_email):
        return None
    if not isinstance(password, str) or not password:
        return None

    user = find_user_by_email(normalized_email)
    if not user or not user.get("active", True):
        return None
    if not check_password_hash(user.get("password_hash", ""), password):
        return None
    return user


def create_access_token(user: dict[str, Any], profile: str) -> tuple[str, int]:
    normalized_profile = normalize_profile(profile)
    if normalized_profile not in normalize_profiles(user.get("profiles")):
        raise AuthError("Perfil nao permitido para este usuario", 403)

    expires_in = int(settings.auth_token_expiration_minutes) * 60
    now = _utcnow()
    payload = {
        "sub": user.get("id"),
        "email": user.get("email"),
        "profile": normalized_profile,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }

    secret = get_auth_secret()
    if pyjwt:
        token = pyjwt.encode(payload, secret, algorithm="HS256")
    else:
        token = _fallback_jwt_encode(payload, secret)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    if not token:
        raise AuthError("Token obrigatorio", 401)

    secret = get_auth_secret()
    try:
        if pyjwt:
            return pyjwt.decode(token, secret, algorithms=["HS256"])
        return _fallback_jwt_decode(token, secret)
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError("Token invalido", 401) from exc


def get_user_from_token(token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = decode_access_token(token)
    user = find_user_by_id(payload.get("sub"))
    profile = normalize_profile(payload.get("profile"))

    if not user or not user.get("active", True):
        raise AuthError("Token invalido", 401)
    if profile not in normalize_profiles(user.get("profiles")):
        raise AuthError("Perfil nao permitido para este usuario", 403)

    return user, payload


def user_has_profile(user: dict[str, Any], profile: str) -> bool:
    return normalize_profile(profile) in normalize_profiles(user.get("profiles"))


def profile_has_permission(profile: str, permission: str) -> bool:
    return permission in PROFILE_PERMISSIONS.get(normalize_profile(profile), set())
