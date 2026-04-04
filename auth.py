import os
import jwt
from functools import wraps
from flask import request, jsonify
from datetime import datetime, timedelta, timezone

JWT_SECRET = os.getenv("JWT_SECRET", "review-analyzer-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def generate_token(payload: dict) -> str:
    """Generate a JWT token with expiration."""
    payload = payload.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload["iat"] = datetime.now(timezone.utc)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def require_auth(f):
    """Decorator to require valid JWT in Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header:
            return jsonify({"error": "Missing Authorization header"}), 401

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return jsonify({"error": "Invalid Authorization header format. Use: Bearer <token>"}), 401

        token = parts[1]
        try:
            decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.jwt_payload = decoded
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return decorated
