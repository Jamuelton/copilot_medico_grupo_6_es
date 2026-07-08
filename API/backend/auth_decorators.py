from functools import wraps

from flask import g, jsonify, request

from .auth_service import AuthError, get_user_from_token, normalize_profile, sanitize_user


def _extract_bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return ""
    return auth_header.removeprefix("Bearer ").strip()


def token_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        try:
            user, payload = get_user_from_token(_extract_bearer_token())
            g.current_user = user
            g.current_user_safe = sanitize_user(user)
            g.current_profile = normalize_profile(payload.get("profile"))
            g.current_token_payload = payload
        except AuthError as exc:
            return jsonify({"status": "error", "message": exc.message}), exc.status_code

        return view_func(*args, **kwargs)

    return wrapper


def roles_required(*allowed_profiles: str):
    allowed = {normalize_profile(profile) for profile in allowed_profiles}

    def decorator(view_func):
        @wraps(view_func)
        @token_required
        def wrapper(*args, **kwargs):
            current_profile = getattr(g, "current_profile", "")
            if current_profile not in allowed:
                return jsonify({"status": "error", "message": "Permissao insuficiente"}), 403
            return view_func(*args, **kwargs)

        return wrapper

    return decorator
