import base64
import logging
import httpx
from fastapi import APIRouter, HTTPException, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])


def _decode_token(token: str) -> str:
    padding = "=" * (-len(token) % 4)
    try:
        return base64.urlsafe_b64decode((token + padding).encode("utf-8")).decode("utf-8")
    except Exception as exc:  # pragma: no cover - defensive path
        logger.warning("Token de media inválido | token=%s | exc=%s", token, exc)
        raise HTTPException(status_code=400, detail="invalid_token") from exc


def _validate_target(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="unsupported_scheme")
    return url


def _async_client() -> httpx.AsyncClient:
    """Create an async client pointing Whapi to our proxy."""

    return httpx.AsyncClient(timeout=15.0, follow_redirects=True)


def _content_type(response: httpx.Response) -> str:
    return response.headers.get("Content-Type") or "application/octet-stream"


@router.head("/{token}")
async def proxy_media_head(token: str) -> Response:
    target = _validate_target(_decode_token(token))
    try:
        async with _async_client() as client:
            remote = await client.head(target)
    except httpx.RequestError as exc:  # pragma: no cover - network issues
        logger.warning("HEAD upstream error | target=%s | exc=%s", target, exc)
        raise HTTPException(status_code=502, detail="upstream_unreachable") from exc

    if remote.status_code == 405:  # Method not allowed, asumimos que GET sí funcionará
        return Response(status_code=200)
    if remote.status_code >= 400:
        logger.warning(
            "HEAD upstream non-success | target=%s | status=%s",
            target,
            remote.status_code,
        )
        raise HTTPException(status_code=502, detail="upstream_error")

    headers = {}
    length = remote.headers.get("Content-Length")
    if length:
        headers["Content-Length"] = length
    return Response(status_code=200, media_type=_content_type(remote), headers=headers)


@router.get("/{token}")
async def proxy_media(token: str) -> Response:
    target = _validate_target(_decode_token(token))
    try:
        async with _async_client() as client:
            remote = await client.get(target)
    except httpx.RequestError as exc:  # pragma: no cover - network issues
        logger.warning("GET upstream error | target=%s | exc=%s", target, exc)
        raise HTTPException(status_code=502, detail="upstream_unreachable") from exc

    if remote.status_code >= 400:
        logger.warning(
            "GET upstream non-success | target=%s | status=%s",
            target,
            remote.status_code,
        )
        raise HTTPException(status_code=502, detail="upstream_error")

    return Response(content=remote.content, media_type=_content_type(remote))
