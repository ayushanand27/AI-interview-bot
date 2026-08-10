"""Live interview room REST + WebSocket sync (demo MVP)."""

import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_role
from app.core.exceptions import NotFoundException
from app.core.limiter import (
    CODING_RUN_LIMIT,
    EMAIL_SEND_LIMIT,
    RECRUITER_WRITE_LIMIT,
    limiter,
)
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.common import BaseResponse
from app.schemas.jobs_live import (
    CreateLiveRoomRequest,
    EndLiveRoomRequest,
    LiveRoomPublic,
    LiveRoomSummary,
    LiveRunTestsRequest,
    SendLiveInvitesRequest,
    SendLiveInvitesResponse,
)
from app.services.coding_judge import public_run_payload, run_test_cases
from app.services.email_service import (
    send_live_interview_invite_email,
    smtp_delivery_hint,
)
from app.services.live_interview_service import LiveInterviewService

logger = logging.getLogger("app.api.live")

router = APIRouter(prefix="/live", tags=["Live Interview"])

# In-memory presence/sync for demo (single EC2 process).
_rooms: dict[str, set[WebSocket]] = defaultdict(set)
_room_state: dict[str, dict[str, Any]] = {}


def _join_link(token: str) -> str:
    return f"/live/{token}"


@router.post("/rooms", response_model=BaseResponse[LiveRoomSummary])
@limiter.limit(RECRUITER_WRITE_LIMIT)
async def create_live_room(
    request: Request,
    body: CreateLiveRoomRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    room = await LiveInterviewService(db).create_room(
        current_user.id,
        title=body.title,
        meet_url=body.meet_url,
        problem_text=body.problem_text,
        language=body.language,
        starter_code=body.starter_code,
        public_tests=body.public_tests,
        application_id=body.application_id,
        expiry_hours=body.expiry_hours,
    )
    return BaseResponse(
        success=True,
        message="Live room created",
        data=LiveRoomSummary(
            token=room.token,
            title=room.title,
            meet_url=room.meet_url,
            join_link=_join_link(room.token),
            language=room.language,
            status=room.status,
            expiry_at=room.expiry_at,
            created_at=room.created_at,
            application_id=room.application_id,
        ),
    )


@router.get("/rooms", response_model=BaseResponse[list[LiveRoomSummary]])
async def list_live_rooms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    rooms = await LiveInterviewService(db).list_rooms(current_user.id)
    data = [
        LiveRoomSummary(
            token=r.token,
            title=r.title,
            meet_url=r.meet_url,
            join_link=_join_link(r.token),
            language=r.language,
            status=r.status,
            expiry_at=r.expiry_at,
            created_at=r.created_at,
            application_id=r.application_id,
        )
        for r in rooms
    ]
    return BaseResponse(success=True, message="OK", data=data)


@router.get("/rooms/{token}", response_model=BaseResponse[LiveRoomPublic])
async def get_live_room(token: str, db: AsyncSession = Depends(get_db)):
    room = await LiveInterviewService(db).get_room(token)
    return BaseResponse(
        success=True,
        message="OK",
        data=LiveRoomPublic(
            token=room.token,
            title=room.title,
            meet_url=room.meet_url,
            problem_text=room.problem_text,
            starter_code=room.starter_code,
            language=room.language,
            public_tests=list(room.public_tests_json or []),
            status=room.status,
            expiry_at=room.expiry_at,
        ),
    )


@router.post("/rooms/{token}/run-tests", response_model=BaseResponse[dict])
@limiter.limit(CODING_RUN_LIMIT)
async def run_live_tests(
    request: Request,
    token: str,
    body: LiveRunTestsRequest,
    db: AsyncSession = Depends(get_db),
):
    room = await LiveInterviewService(db).get_room(token)
    tests = body.public_tests or list(room.public_tests_json or [])
    summary = run_test_cases(
        language=body.language or room.language,
        source=body.source,
        tests=tests,
    )
    return BaseResponse(
        success=True,
        message="Tests finished",
        data=public_run_payload(summary),
    )


@router.post(
    "/rooms/{token}/send-invites",
    response_model=BaseResponse[SendLiveInvitesResponse],
)
@limiter.limit(EMAIL_SEND_LIMIT)
async def send_live_invites(
    request: Request,
    token: str,
    body: SendLiveInvitesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    service = LiveInterviewService(db)
    room = await service.get_room(token)
    if room.recruiter_id != current_user.id:
        raise NotFoundException("Live room not found")

    live_path = f"/live/{room.token}?role=candidate"
    live_url = f"{settings.effective_frontend_url}{live_path}"
    sent = 0
    failed: list[str] = []
    for email in body.emails:
        ok = send_live_interview_invite_email(
            str(email),
            candidate_name=body.candidate_name or "Candidate",
            room_title=room.title,
            live_url=live_url,
            meet_url=room.meet_url,
            recruiter_note=body.message,
        )
        if ok:
            sent += 1
        else:
            failed.append(str(email))
    note = smtp_delivery_hint(any_failed=bool(failed))
    msg = f"Sent {sent} invite(s)"
    if failed:
        msg += f"; {len(failed)} failed"
    return BaseResponse(
        success=True,
        message=msg,
        data=SendLiveInvitesResponse(
            sent=sent,
            failed=failed,
            delivery_note=note,
            live_link=live_path,
            meet_url=room.meet_url,
        ),
    )


@router.post("/rooms/{token}/end", response_model=BaseResponse[LiveRoomSummary])
async def end_live_room(
    token: str,
    body: EndLiveRoomRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.RECRUITER.value)),
):
    room = await LiveInterviewService(db).end_room(
        current_user.id,
        token,
        final_code=body.final_code,
        notes=body.notes,
    )
    return BaseResponse(
        success=True,
        message="Room ended",
        data=LiveRoomSummary(
            token=room.token,
            title=room.title,
            meet_url=room.meet_url,
            join_link=_join_link(room.token),
            language=room.language,
            status=room.status,
            expiry_at=room.expiry_at,
            created_at=room.created_at,
            application_id=room.application_id,
        ),
    )


async def _broadcast(token: str, payload: dict, exclude: WebSocket | None = None) -> None:
    dead: list[WebSocket] = []
    for ws in list(_rooms.get(token, set())):
        if ws is exclude:
            continue
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _rooms[token].discard(ws)


@router.websocket("/ws/{token}")
async def live_room_ws(
    websocket: WebSocket,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        await LiveInterviewService(db).get_room(token)
    except Exception:
        await websocket.close(code=4404, reason="Room not found or expired")
        return

    await websocket.accept()
    role = websocket.query_params.get("role", "candidate")
    name = websocket.query_params.get("name", role)
    _rooms[token].add(websocket)
    state = _room_state.setdefault(
        token,
        {"code": None, "language": None, "chat": [], "presence": {}},
    )
    state["presence"][role] = name
    try:
        await websocket.send_text(
            json.dumps({"type": "hello", "state": state, "role": role})
        )
        await _broadcast(
            token,
            {"type": "presence", "presence": state["presence"]},
            exclude=None,
        )
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            mtype = msg.get("type")
            if mtype == "code":
                state["code"] = msg.get("code")
                state["language"] = msg.get("language") or state.get("language")
                await _broadcast(
                    token,
                    {
                        "type": "code",
                        "code": state["code"],
                        "language": state["language"],
                        "from": role,
                    },
                    exclude=websocket,
                )
            elif mtype == "chat":
                item = {
                    "from": name,
                    "role": role,
                    "text": str(msg.get("text") or "")[:2000],
                }
                state["chat"] = (state.get("chat") or [])[-40:] + [item]
                await _broadcast(token, {"type": "chat", "message": item})
            elif mtype == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("live ws error token=%s: %s", token, exc)
    finally:
        _rooms[token].discard(websocket)
        if role in state.get("presence", {}):
            del state["presence"][role]
        await _broadcast(token, {"type": "presence", "presence": state.get("presence", {})})
        if not _rooms[token]:
            _rooms.pop(token, None)
