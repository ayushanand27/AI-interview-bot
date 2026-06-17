"""Business logic for candidate invite link flow."""

from __future__ import annotations

import base64
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.db.candidate_verification_model import CandidateVerification
from app.db.interview_invite_model import InterviewInvite
from app.db.session_model import Session as DBSession
from app.models.schemas import SessionStatus
from app.models.user import User, UserRole
from app.schemas.invite import (
    InviteInvalidResponse,
    InviteLoginRequest,
    InviteRegisterRequest,
    InviteRegisterResponse,
    InviteValidResponse,
    InviteVerifyIdentityRequest,
    InviteVerifyIdentityResponse,
)
from app.services.identity_verification import verify_faces_from_base64


def _difficulty_to_experience(difficulty: str) -> str:
    mapping = {"Easy": "junior", "Medium": "mid", "Hard": "senior"}
    return mapping.get(difficulty, "mid")


def _role_title_from_jd(jd_text: str) -> str:
    for line in jd_text.splitlines():
        cleaned = line.strip()
        if cleaned and len(cleaned) > 3:
            return cleaned[:255]
    return "Interview Position"


def _decode_image_bytes(data: str) -> bytes:
    raw = data.strip()
    if "," in raw:
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


class InviteService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_invite(self, token: str) -> InterviewInvite | None:
        result = await self.db.execute(
            select(InterviewInvite).where(InterviewInvite.token == token)
        )
        return result.scalar_one_or_none()

    async def _get_recruiter_company(self, recruiter_id: int) -> str:
        result = await self.db.execute(select(User).where(User.id == recruiter_id))
        recruiter = result.scalar_one_or_none()
        if recruiter is None:
            return "Hiring Company"
        return recruiter.full_name

    def _validate_invite_row(
        self, invite: InterviewInvite | None
    ) -> InviteInvalidResponse | None:
        if invite is None:
            return InviteInvalidResponse(reason="This invite link is invalid.")

        now = datetime.now(timezone.utc)
        expiry = invite.expiry_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        if expiry <= now:
            return InviteInvalidResponse(reason="This link has expired.")

        if invite.used_count >= invite.max_uses:
            return InviteInvalidResponse(reason="This invite link has reached its usage limit.")

        return None

    async def check_invite(self, token: str) -> InviteValidResponse | InviteInvalidResponse:
        invite = await self._get_invite(token)
        invalid = self._validate_invite_row(invite)
        if invalid is not None:
            return invalid
        assert invite is not None

        company = await self._get_recruiter_company(invite.recruiter_id)
        questions = list(invite.questions_json or [])
        return InviteValidResponse(
            role_title=_role_title_from_jd(invite.jd_text),
            company=company,
            question_count=len(questions),
            difficulty=invite.difficulty,
        )

    async def _resume_existing_registration(
        self, token: str, email: str
    ) -> InviteRegisterResponse | None:
        """Return tokens for an existing token+email registration (page refresh)."""
        result = await self.db.execute(
            select(CandidateVerification).where(
                CandidateVerification.token == token,
                CandidateVerification.email == str(email),
            )
        )
        verification = result.scalar_one_or_none()
        if verification is None or not verification.session_id:
            return None

        user_result = await self.db.execute(
            select(User).where(User.email == email)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            return None

        return InviteRegisterResponse(
            session_id=UUID(verification.session_id),
            access_token=create_access_token(user_id=user.id, role=user.role.value),
            refresh_token=create_refresh_token(user_id=user.id),
        )

    async def _attach_candidate_to_invite(
        self,
        invite: InterviewInvite,
        token: str,
        user: User,
        name: str,
        email: str,
        phone: str,
    ) -> InviteRegisterResponse:
        questions = [str(q).strip() for q in (invite.questions_json or []) if str(q).strip()]
        if not questions:
            raise BadRequestException("This invite has no interview questions configured.")

        now = datetime.now(timezone.utc)
        session_id = uuid4()
        role_title = _role_title_from_jd(invite.jd_text)
        experience_level = _difficulty_to_experience(invite.difficulty)

        db_session = DBSession(
            session_id=session_id,
            user_id=user.id,
            role_title=role_title,
            experience_level=experience_level,
            topic_focus=None,
            status=SessionStatus.QUESTIONS_READY.value,
            questions=questions,
            answers=[],
            answer_judgments=[],
            current_question_index=0,
            total_questions=len(questions),
            created_at=now,
            updated_at=now,
            resume_filename=None,
            resume_text=None,
            job_description=invite.jd_text,
            final_score=None,
            proctoring_summary=None,
            recording_filename=None,
            recording_mp4_filename=None,
        )
        self.db.add(db_session)

        verification = CandidateVerification(
            token=token,
            candidate_name=name.strip(),
            email=str(email),
            phone=phone.strip(),
            verified=False,
            session_id=str(session_id),
            created_at=now,
        )
        self.db.add(verification)

        invite.used_count = int(invite.used_count) + 1
        await self.db.commit()

        access_token = create_access_token(user_id=user.id, role=user.role.value)
        refresh_token = create_refresh_token(user_id=user.id)

        return InviteRegisterResponse(
            session_id=session_id,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    async def register_candidate(
        self, token: str, data: InviteRegisterRequest
    ) -> InviteRegisterResponse:
        invite = await self._get_invite(token)
        invalid = self._validate_invite_row(invite)
        if invalid is not None:
            raise BadRequestException(invalid.reason)

        assert invite is not None

        existing_registration = await self._resume_existing_registration(
            token, str(data.email)
        )
        if existing_registration is not None:
            return existing_registration

        existing_user = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        if existing_user.scalar_one_or_none() is not None:
            raise ConflictException(
                "An account with this email already exists. Log in below to continue this interview."
            )

        password = secrets.token_urlsafe(16)
        user = User(
            full_name=data.name.strip(),
            email=data.email,
            hashed_password=hash_password(password),
            role=UserRole.CANDIDATE,
            is_active=True,
        )
        self.db.add(user)
        await self.db.flush()

        return await self._attach_candidate_to_invite(
            invite=invite,
            token=token,
            user=user,
            name=data.name,
            email=str(data.email),
            phone=data.phone,
        )

    async def login_candidate(
        self, token: str, data: InviteLoginRequest
    ) -> InviteRegisterResponse:
        invite = await self._get_invite(token)
        invalid = self._validate_invite_row(invite)
        if invalid is not None:
            raise BadRequestException(invalid.reason)

        assert invite is not None

        existing_registration = await self._resume_existing_registration(
            token, str(data.email)
        )
        if existing_registration is not None:
            return existing_registration

        result = await self.db.execute(select(User).where(User.email == data.email))
        user = result.scalar_one_or_none()
        if user is None or not verify_password(data.password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password")

        if not user.is_active:
            raise UnauthorizedException("Your account has been deactivated")

        if user.role != UserRole.CANDIDATE:
            raise ForbiddenException(
                "This invite link is for candidates only. Please use a candidate account."
            )

        return await self._attach_candidate_to_invite(
            invite=invite,
            token=token,
            user=user,
            name=user.full_name,
            email=str(data.email),
            phone=data.phone,
        )

    async def verify_identity(
        self, token: str, data: InviteVerifyIdentityRequest
    ) -> InviteVerifyIdentityResponse:
        invite = await self._get_invite(token)
        invalid = self._validate_invite_row(invite)
        if invalid is not None:
            raise BadRequestException(invalid.reason)

        result = await self.db.execute(
            select(CandidateVerification).where(
                CandidateVerification.token == token,
                CandidateVerification.session_id == str(data.session_id),
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise NotFoundException("Registration not found for this invite and session.")

        upload_dir = Path(settings.UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)

        id_path = upload_dir / f"{token}_id.jpg"
        selfie_path = upload_dir / f"{token}_selfie.jpg"

        try:
            id_path.write_bytes(_decode_image_bytes(data.id_image_base64))
            selfie_path.write_bytes(_decode_image_bytes(data.selfie_base64))
        except (ValueError, OSError) as exc:
            raise BadRequestException("Invalid image data provided.") from exc

        verification = verify_faces_from_base64(data.id_image_base64, data.selfie_base64)

        record.id_document_path = id_path.name
        record.selfie_path = selfie_path.name
        record.verified = verification.verified
        record.confidence_score = verification.confidence
        await self.db.commit()

        return InviteVerifyIdentityResponse(
            verified=verification.verified,
            confidence=verification.confidence,
            message=verification.message,
        )
