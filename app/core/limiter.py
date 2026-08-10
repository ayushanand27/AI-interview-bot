"""Shared SlowAPI limiter and rate-limit strings for route decorators."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

AUTH_REGISTER_LIMIT = "5/minute"
AUTH_LOGIN_LIMIT = "10/minute"
PROCTOR_ANALYZE_LIMIT = "30/minute"
INTERVIEW_LIMIT = "60/minute"
DOCS_LIMIT = "20/minute"
JOB_APPLY_LIMIT = "10/minute"
RECRUITER_WRITE_LIMIT = "20/minute"
EMAIL_SEND_LIMIT = "10/minute"
LLM_GENERATE_LIMIT = "10/minute"
INVITE_LOGIN_LIMIT = "10/minute"
INVITE_REGISTER_LIMIT = "10/minute"
IDENTITY_VERIFY_LIMIT = "6/minute"
CODING_RUN_LIMIT = "20/minute"
STATUS_LIMIT = "20/minute"
PRIVACY_LIMIT = "10/minute"
