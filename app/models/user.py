# app/models/user.py
# ─────────────────────────────────────────────────────────────
# Users table — stores all registered users.
# Role field determines candidate vs recruiter access.
# One user can have many interviews and one resume.
# ─────────────────────────────────────────────────────────────

from sqlalchemy import String, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
import enum

from app.db.base import Base


class UserRole(str, enum.Enum):
    """
    User roles — controls what each user can access.
    candidate  → takes interviews
    recruiter  → creates and monitors interviews
    """
    CANDIDATE = "candidate"
    RECRUITER = "recruiter"


class User(Base):
    __tablename__ = "users"

    # ── Primary Key ───────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # ── Identity ──────────────────────────────────────────
    # unique=True ensures no two users share an email
    # index=True speeds up login queries (lookup by email)
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Auth ──────────────────────────────────────────────
    # Never store plain passwords — only bcrypt hashes
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Role ──────────────────────────────────────────────
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole),
        default=UserRole.CANDIDATE,
        nullable=False
    )

    # ── Status ────────────────────────────────────────────
    # is_active=False = soft delete / banned account
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    verification_token_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reset_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reset_token_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Timestamps ────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    # ── Relationships ─────────────────────────────────────
    # interviews and resume relationships added back when those modules are built
    
    # # ── Relationships ─────────────────────────────────────
    # # back_populates links both sides of the relationship
    # # lazy="selectin" auto-loads related data efficiently
    # interviews: Mapped[list["Interview"]] = relationship(
    #     "Interview",
    #     back_populates="user",
    #     lazy="selectin"
    # )
    # resume: Mapped["Resume"] = relationship(
    #     "Resume",
    #     back_populates="user",
    #     uselist=False,  # One user = one resume
    #     lazy="selectin"
    # )

    # def __repr__(self) -> str:
    #     return f"<User id={self.id} email={self.email} role={self.role}>"