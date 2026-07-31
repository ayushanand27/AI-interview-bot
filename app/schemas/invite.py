"""Schemas for candidate invite link flow."""

from typing import Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class InviteValidResponse(BaseModel):
    valid: Literal[True] = True
    role_title: str
    company: str
    question_count: int
    difficulty: str


class InviteInvalidResponse(BaseModel):
    valid: Literal[False] = False
    reason: str


InviteCheckResponse = Union[InviteValidResponse, InviteInvalidResponse]


class InviteRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    phone: str = Field(default="")
    password: Optional[str] = Field(default=None, min_length=8)


class InviteRegisterResponse(BaseModel):
    session_id: UUID
    access_token: str
    refresh_token: str


class InviteLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)
    phone: str = Field(default="")


class InviteVerifyIdentityRequest(BaseModel):
    id_image_base64: str
    selfie_base64: str
    selfie_frames_base64: list[str] = Field(default_factory=list)
    liveness_actions: list[str] = Field(default_factory=list)
    session_id: UUID


class InviteVerifyIdentityResponse(BaseModel):
    verified: bool
    confidence: float
    message: str
    low_identity_confidence: bool = False
    liveness_passed: bool = False
    liveness_confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    ocr_name_match: Optional[bool] = None
    ocr_name_detected: Optional[str] = None
    ocr_document_number: Optional[str] = None
