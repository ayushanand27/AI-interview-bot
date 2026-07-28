"""Business logic for candidate invite link flow."""

from __future__ import annotations

import base64
import secrets
from datetime import datetime, timedelta, timezone
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
from app.db.evidence_model import (
    IdentityVerificationAttempt,
    SessionArtifact,
    SessionReviewState,
)
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
from app.services.email_service import send_invite_welcome_password_email
from app.services.question_utils import normalize_questions


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
        questions = normalize_questions(list(invite.questions_json or []))
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
        questions = normalize_questions(list(invite.questions_json or []))
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
            invite_token=token,
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
        reset_token = str(uuid4())
        reset_expiry = datetime.now(timezone.utc) + timedelta(hours=24)
        user = User(
            full_name=data.name.strip(),
            email=data.email,
            hashed_password=hash_password(password),
            role=UserRole.CANDIDATE,
            is_active=True,
            is_verified=True,
            reset_token=reset_token,
            reset_token_expiry=reset_expiry,
        )
        self.db.add(user)
        await self.db.flush()

        response = await self._attach_candidate_to_invite(
            invite=invite,
            token=token,
            user=user,
            name=data.name,
            email=str(data.email),
            phone=data.phone,
        )
        send_invite_welcome_password_email(
            str(data.email),
            data.name.strip(),
            reset_token,
        )
        return response

    async def login_candidate(
        self, token: str, data: InviteLoginRequest
    ) -> InviteRegisterResponse:
        invite = await self._get_invite(token)
        invalid = self._validate_invite_row(invite)
        if invalid is not None:
            raise BadRequestException(invalid.reason)

        assert invite is not None

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

        user.is_verified = True

        existing_registration = await self._resume_existing_registration(
            token, str(data.email)
        )
        if existing_registration is not None:
            return existing_registration

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
        await self.db.flush()

        id_artifact = SessionArtifact(
            artifact_type="identity_id_image",
            session_id=data.session_id,
            candidate_verification_id=record.id,
            storage_path=id_path.name,
            mime_type="image/jpeg",
            file_size_bytes=id_path.stat().st_size if id_path.exists() else None,
            metadata_json={"token": token, "source": "invite_identity"},
            created_at=datetime.now(timezone.utc),
        )
        selfie_artifact = SessionArtifact(
            artifact_type="identity_selfie_image",
            session_id=data.session_id,
            candidate_verification_id=record.id,
            storage_path=selfie_path.name,
            mime_type="image/jpeg",
            file_size_bytes=selfie_path.stat().st_size if selfie_path.exists() else None,
            metadata_json={"token": token, "source": "invite_identity"},
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(id_artifact)
        self.db.add(selfie_artifact)
        await self.db.flush()

        self.db.add(
            IdentityVerificationAttempt(
            candidate_verification_id=record.id,
            token=token,
            session_id=str(data.session_id),
            verified=verification.verified,
            confidence_score=verification.confidence,
            low_identity_confidence=verification.low_identity_confidence,
            similarity_score=verification.similarity_score,
            message=verification.message,
            id_artifact_id=id_artifact.id,
            selfie_artifact_id=selfie_artifact.id,
            created_at=datetime.now(timezone.utc),
        )
        )

        if verification.low_identity_confidence:
            session_row = await self.db.get(DBSession, data.session_id)
            if session_row is not None:
                summary = dict(session_row.proctoring_summary or {})
                summary["low_identity_confidence"] = True
                summary["identity_similarity_score"] = round(
                    verification.similarity_score, 4
                )
                session_row.proctoring_summary = summary
                session_row.human_review_flag = True
                review_state = (
                    await self.db.execute(
                        select(SessionReviewState).where(
                            SessionReviewState.session_id == data.session_id
                        )
                    )
                ).scalar_one_or_none()
                if review_state is None:
                    review_state = SessionReviewState(
                        session_id=data.session_id,
                        human_review_required=True,
                        review_status="needs_review",
                        review_notes="Identity verification confidence below threshold.",
                        reviewed_at=None,
                        reviewed_by_user_id=None,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    self.db.add(review_state)
                else:
                    review_state.human_review_required = True
                    review_state.review_status = "needs_review"
                    review_state.review_notes = (
                        "Identity verification confidence below threshold."
                    )
                    review_state.updated_at = datetime.now(timezone.utc)

        await self.db.commit()

        return InviteVerifyIdentityResponse(
            verified=verification.verified,
            confidence=verification.confidence,
            message=verification.message,
            low_identity_confidence=verification.low_identity_confidence,
        )
