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
    session_id: UUID


class InviteVerifyIdentityResponse(BaseModel):
    verified: bool
    confidence: float
    message: str
