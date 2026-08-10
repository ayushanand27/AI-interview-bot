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
