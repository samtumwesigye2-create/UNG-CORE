import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.api.security import SESSION_COOKIE
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
CLIENT_ID = "UNG-CORE"
CALLBACK_PATH = "/auth/callback"
STATE_COOKIE = "ung_core_sso_state"
VERIFIER_COOKIE = "ung_core_pkce_verifier"


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _callback_url(request: Request) -> str:
    base = settings.public_base_url.strip().rstrip("/")
    if not base:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
        if forwarded_proto and forwarded_host:
            base = f"{forwarded_proto}://{forwarded_host}"
        else:
            base = str(request.base_url).rstrip("/")
    return base + CALLBACK_PATH


@router.get("/login", include_in_schema=False)
async def login(request: Request):
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(32)
    params = urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": _callback_url(request),
        "code_challenge": _challenge(verifier),
        "state": state,
    })
    response = RedirectResponse(f"{settings.iam_base_url}/sso/launch?{params}", status_code=302)
    for name, value in ((STATE_COOKIE, state), (VERIFIER_COOKIE, verifier)):
        response.set_cookie(name, value, max_age=300, httponly=True, secure=True, samesite="lax", path="/")
    return response


@router.get("/callback", include_in_schema=False)
async def callback(request: Request, code: str, state: str):
    expected_state = request.cookies.get(STATE_COOKIE)
    verifier = request.cookies.get(VERIFIER_COOKIE)
    if not expected_state or not verifier or not secrets.compare_digest(expected_state, state):
        raise HTTPException(400, "SSO state validation failed")
    body = {
        "client_id": CLIENT_ID,
        "redirect_uri": _callback_url(request),
        "code": code,
        "code_verifier": verifier,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(f"{settings.iam_base_url}/v1/sso/token", json=body)
    if response.status_code != 200:
        raise HTTPException(401, "UNG-IAM sign-in failed")
    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(401, "UNG-IAM did not issue a session")
    result = RedirectResponse("/v1/control-center/ui", status_code=302)
    result.set_cookie(
        SESSION_COOKIE,
        access_token,
        max_age=int(token_data.get("expires_in") or 28800),
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    result.delete_cookie(STATE_COOKIE, path="/")
    result.delete_cookie(VERIFIER_COOKIE, path="/")
    return result


@router.get("/logout", include_in_schema=False)
async def logout():
    response = RedirectResponse("/v1/control-center/ui", status_code=302)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
