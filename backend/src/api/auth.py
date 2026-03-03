"""Auth0 JWT 検証ユーティリティ

FastAPI 依存性として使用する:
    from src.api.auth import require_auth
    @router.get("/protected")
    def protected(claims: dict = Depends(require_auth)):
        return {"sub": claims["sub"]}
"""
import logging
import os
from functools import lru_cache
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=True)


@lru_cache(maxsize=1)
def _get_jwks() -> dict[str, Any]:
    """Auth0 JWKS エンドポイントから公開鍵セットを取得する (起動後キャッシュ)。"""
    domain = os.environ["AUTH0_DOMAIN"]
    url = f"https://{domain}/.well-known/jwks.json"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _verify_token(token: str) -> dict[str, Any]:
    """JWT を検証してクレームを返す。"""
    domain = os.environ["AUTH0_DOMAIN"]
    audience = os.environ["AUTH0_AUDIENCE"]

    try:
        jwks = _get_jwks()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")

        # 対応する公開鍵を JWKS から検索
        key = None
        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
                break

        if key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="公開鍵が見つかりません",
            )

        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=audience,
            issuer=f"https://{domain}/",
        )
        return claims

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンの有効期限が切れています",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"無効なトークン: {e}",
        )


def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    """認証必須エンドポイントに使う FastAPI 依存性。クレームを返す。"""
    return _verify_token(credentials.credentials)
