import importlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import (
    WebRTCGrantPublic,
    WebRTCGrantRefreshReq,
    WebRTCGrantRevokeReq,
    WebRTCOfferPublic,
    WebRTCOfferReq,
    WebRTCRevokePublic,
)
from ..redis_client import redis_client
from ..services.device_services import get_devices_with_details
from ..services.services import verify_api_key

# aiortc is optional — server can run without it, just WebRTC endpoints will 503
RTCPeerConnection: Any = None
RTCSessionDescription: Any = None
MediaPlayer: Any = None

try:
    aiortc_module = importlib.import_module("aiortc")
    aiortc_media = importlib.import_module("aiortc.contrib.media")
    RTCPeerConnection = aiortc_module.RTCPeerConnection
    RTCSessionDescription = aiortc_module.RTCSessionDescription
    MediaPlayer = aiortc_media.MediaPlayer
except ImportError:
    pass

router = APIRouter(prefix="/api/server", tags=["webrtc"])

GRANT_TTL = 300

# device_name -> active PC / player
_connections: dict[str, Any] = {}
_players: dict[str, Any] = {}


def _grant_key(token: str) -> str:
    return f"webrtc:grant:{token}"


def _parse_grant_token(grant_token: str | None) -> str:
    if not grant_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="grant_token header is required",
        )
    token = grant_token.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Grant token is missing",
        )
    return token


def _load_grant(token: str) -> dict:
    raw = redis_client.get(_grant_key(token))
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired grant token",
        )
    grant = json.loads(raw)
    if grant.get("revoked"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Grant token has been revoked",
        )
    return grant


def _validate_grant_for_device(
    device_name: str,
    grant_token: str | None = None,
) -> tuple[str, dict]:
    token = _parse_grant_token(grant_token)
    grant = _load_grant(token)
    if grant.get("device_name") != device_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grant token does not belong to this device",
        )
    return token, grant


def _issue_grant(device_name: str, ttl: int = GRANT_TTL) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    expires_str = expires_at.isoformat().replace("+00:00", "Z")
    redis_client.setex(
        _grant_key(token),
        ttl,
        json.dumps({"device_name": device_name, "expires_at": expires_str, "revoked": False}),
    )
    return token, expires_str


async def _close_peer(device_name: str):
    pc = _connections.pop(device_name, None)
    _players.pop(device_name, None)
    if pc:
        await pc.close()


async def _check_device_exists(session: AsyncSession, device_name: str):
    devices = await get_devices_with_details(session)
    for d in devices:
        if d.name == device_name:
            return d
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Device '{device_name}' not found",
    )


@router.post("/devices/{device_name}/webrtc/grants", response_model=WebRTCGrantPublic)
async def create_webrtc_grant(device_name: str, _: None = Depends(verify_api_key)):
    token, expires_at = _issue_grant(device_name)
    return {"device_name": device_name, "grant_token": token, "expires_at": expires_at}


@router.post("/devices/{device_name}/webrtc/grants/refresh", response_model=WebRTCGrantPublic)
async def refresh_webrtc_grant(
    device_name: str,
    body: WebRTCGrantRefreshReq,
    _: None = Depends(verify_api_key),
):
    grant = _load_grant(body.grant_token)
    if grant.get("device_name") != device_name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grant token does not belong to this device",
        )

    redis_client.delete(_grant_key(body.grant_token))
    token, expires_at = _issue_grant(device_name)
    return {"device_name": device_name, "grant_token": token, "expires_at": expires_at}


@router.post("/webrtc/grants/revoke", response_model=WebRTCRevokePublic)
async def revoke_webrtc_grant(body: WebRTCGrantRevokeReq, _: None = Depends(verify_api_key)):
    raw = redis_client.get(_grant_key(body.grant_token))
    if raw:
        data = json.loads(raw)
        if dev := data.get("device_name"):
            await _close_peer(dev)
    redis_client.delete(_grant_key(body.grant_token))
    return {"status": "revoked"}


@router.post("/devices/{device_name}/webrtc/offer", response_model=WebRTCOfferPublic)
async def create_webrtc_offer(
    device_name: str,
    body: WebRTCOfferReq,
    grant_token: str | None = Header(default=None, alias="grant_token"),
    session: AsyncSession = Depends(get_session),
):
    if not RTCPeerConnection or not RTCSessionDescription or not MediaPlayer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="aiortc is not installed on the server",
        )

    _, _ = _validate_grant_for_device(device_name, grant_token)

    await _check_device_exists(session, device_name)

    stream_url = os.getenv("USTREAM_URL")
    if not stream_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="USTREAM_URL is not configured",
        )

    await _close_peer(device_name)

    try:
        player = MediaPlayer(stream_url, format="mjpeg")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to open uStreamer feed: {exc}",
        )

    if not player.video:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="uStreamer feed does not provide a video track",
        )

    pc = RTCPeerConnection()
    pc.addTrack(player.video)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        if pc.connectionState in {"failed", "closed", "disconnected"}:
            await _close_peer(device_name)

    try:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=body.sdp, type=body.type))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
    except Exception as exc:
        await pc.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid WebRTC offer: {exc}",
        )

    _connections[device_name] = pc
    _players[device_name] = player

    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


@router.post("/devices/{device_name}/webrtc/stop", response_model=WebRTCRevokePublic)
async def stop_webrtc_offer(
    device_name: str,
    grant_token: str | None = Header(default=None, alias="grant_token"),
):
    token, _ = _validate_grant_for_device(device_name, grant_token)

    await _close_peer(device_name)
    redis_client.delete(_grant_key(token))
    return {"status": "revoked"}
