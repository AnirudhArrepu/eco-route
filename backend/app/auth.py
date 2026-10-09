from functools import lru_cache

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

from app.config import settings


def cognito_issuer() -> str:
    if not settings.cognito_user_pool_id:
        raise HTTPException(503, "Cognito user pool is not configured")
    return f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}"


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, cache_keys=True, timeout=5)


def authenticated_user(authorization: str | None = Header(default=None)) -> str | None:
    required = settings.auth_required or settings.environment.lower() == "production"
    if not authorization:
        if required:
            raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    if not settings.cognito_user_pool_id or not settings.cognito_app_client_id:
        raise HTTPException(503, "Cognito authentication is not configured")

    issuer = cognito_issuer()
    try:
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise PyJWTError("Empty bearer token")
        jwks = _jwks_client(f"{issuer}/.well-known/jwks.json")
        signing_key = jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
        token_use = claims.get("token_use")
        if token_use == "id":
            if claims.get("aud") != settings.cognito_app_client_id:
                raise PyJWTError("Invalid app audience")
        elif token_use == "access":
            if claims.get("client_id") != settings.cognito_app_client_id:
                raise PyJWTError("Invalid app client")
        else:
            raise PyJWTError("Unsupported Cognito token")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise PyJWTError("Missing subject")
        return subject
    except (PyJWTError, PyJWKClientError, OSError, ValueError) as exc:
        raise HTTPException(401, "Invalid bearer token", headers={"WWW-Authenticate": "Bearer"}) from exc


def resolve_user_id(requested_user_id: str, authenticated_subject: str | None) -> str:
    if authenticated_subject is None:
        return requested_user_id
    if requested_user_id != authenticated_subject:
        raise HTTPException(403, "Authenticated user does not own this resource")
    return authenticated_subject
