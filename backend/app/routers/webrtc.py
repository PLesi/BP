import importlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
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


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _enhance_video_sdp(sdp: str) -> str:
    """Apply conservative bitrate hints for common video codecs in SDP answer."""
    max_kbps = _env_int("WEBRTC_VIDEO_MAX_BITRATE_KBPS", 5000)
    min_kbps = _env_int("WEBRTC_VIDEO_MIN_BITRATE_KBPS", 1200)
    start_kbps = _env_int("WEBRTC_VIDEO_START_BITRATE_KBPS", 2500)

    lines = sdp.split("\r\n")
    if not lines:
        return sdp

    # Locate the first video m-section boundaries.
    m_video_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("m=video "):
            m_video_idx = i
            break
    if m_video_idx == -1:
        return sdp

    section_end = len(lines)
    for i in range(m_video_idx + 1, len(lines)):
        if lines[i].startswith("m="):
            section_end = i
            break

    video_lines = lines[m_video_idx:section_end]

    # Determine payload id for preferred codecs.
    preferred_payload = None
    for codec in ("H264", "VP8", "VP9", "AV1"):
        for vline in video_lines:
            if vline.startswith("a=rtpmap:") and (f" {codec}/" in vline):
                payload = vline.split(":", 1)[1].split(" ", 1)[0].strip()
                preferred_payload = payload
                break
        if preferred_payload:
            break

    if not preferred_payload:
        return sdp

    # Add bandwidth lines once per video section.
    has_as = any(vline.startswith("b=AS:") for vline in video_lines)
    has_tias = any(vline.startswith("b=TIAS:") for vline in video_lines)

    insert_at = 1
    for i, vline in enumerate(video_lines):
        if vline.startswith("c="):
            insert_at = i + 1
            break

    if not has_as:
        video_lines.insert(insert_at, f"b=AS:{max_kbps}")
        insert_at += 1
    if not has_tias:
        video_lines.insert(insert_at, f"b=TIAS:{max_kbps * 1000}")

    # Add or extend fmtp line for selected payload.
    fmtp_prefix = f"a=fmtp:{preferred_payload} "
    fmtp_idx = -1
    for i, vline in enumerate(video_lines):
        if vline.startswith(fmtp_prefix):
            fmtp_idx = i
            break

    bitrate_params = (
        f"x-google-start-bitrate={start_kbps};"
        f"x-google-min-bitrate={min_kbps};"
        f"x-google-max-bitrate={max_kbps}"
    )

    if fmtp_idx != -1:
        current = video_lines[fmtp_idx]
        if "x-google-max-bitrate" not in current:
            separator = ";" if not current.endswith(";") else ""
            video_lines[fmtp_idx] = f"{current}{separator}{bitrate_params}"
    else:
        # Add a new fmtp line after matching rtpmap.
        rtpmap_idx = -1
        for i, vline in enumerate(video_lines):
            if vline.startswith(f"a=rtpmap:{preferred_payload} "):
                rtpmap_idx = i
                break
        if rtpmap_idx != -1:
            video_lines.insert(rtpmap_idx + 1, f"a=fmtp:{preferred_payload} {bitrate_params}")

    lines[m_video_idx:section_end] = video_lines
    return "\r\n".join(lines)


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
    request: Request,
    grant_token: str | None = Header(default=None, alias="grant-token"),
    session: AsyncSession = Depends(get_session),
):
    if not RTCPeerConnection or not RTCSessionDescription or not MediaPlayer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="aiortc is not installed on the server",
        )

    # Backward compatibility for older clients still sending grant_token.
    effective_token = grant_token or request.headers.get("grant_token")
    _, _ = _validate_grant_for_device(device_name, effective_token)

    await _check_device_exists(session, device_name)

    stream_url = os.getenv("USTREAM_URL")
    if not stream_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="USTREAM_URL is not configured",
        )

    await _close_peer(device_name)

    try:
        player = MediaPlayer(stream_url)
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
        tuned_answer = RTCSessionDescription(
            sdp=_enhance_video_sdp(answer.sdp),
            type=answer.type,
        )
        await pc.setLocalDescription(tuned_answer)
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
    request: Request,
    grant_token: str | None = Header(default=None, alias="grant-token"),
):
    # Backward compatibility for older clients still sending grant_token.
    effective_token = grant_token or request.headers.get("grant_token")
    token, _ = _validate_grant_for_device(device_name, effective_token)

    await _close_peer(device_name)
    redis_client.delete(_grant_key(token))
    return {"status": "revoked"}
