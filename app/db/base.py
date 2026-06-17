# app/db/base.py
# ─────────────────────────────────────────────────────────────
# Defines the SQLAlchemy declarative Base class.
# ALL database models must inherit from this Base.
# SQLAlchemy uses Base to track all tables and their structure.
# ─────────────────────────────────────────────────────────────

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import DateTime
from datetime import datetime, timezone


class Base(DeclarativeBase):
    """
    The single Base class for all ORM models.
    Every model file (user.py, interview.py etc.)
    will do: class User(Base): ...

    DeclarativeBase is the SQLAlchemy 2.0 way of defining
    the base — cleaner and fully type-safe compared to the
    old declarative_base() function from SQLAlchemy 1.x.
    """
    pass