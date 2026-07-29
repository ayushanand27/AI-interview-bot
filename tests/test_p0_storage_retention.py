"""P0 storage + retention unit tests (local backend; no AWS required)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.object_storage import ObjectStorage, reset_object_storage_cache
from app.services.retention_service import _is_expired, _ttl_for_artifact_type


def test_local_object_storage_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    # Force settings reload
    from app.core import config

    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "settings", config.get_settings())
    reset_object_storage_cache()

    storage = ObjectStorage()
    assert storage.backend == "local"
    key = storage.put_bytes("demo/file.txt", b"hello", content_type="text/plain")
    assert key == "demo/file.txt"
    assert storage.exists(key)
    assert storage.get_bytes(key) == b"hello"
    path = storage.resolve_local_path(key)
    assert path.is_file()
    assert storage.delete(key) is True
    assert not storage.exists(key)

    reset_object_storage_cache()
    config.get_settings.cache_clear()


def test_retention_ttl_by_type():
    assert _ttl_for_artifact_type("identity_id_image") > 0
    assert _ttl_for_artifact_type("session_recording_webm") > 0
    assert _ttl_for_artifact_type("candidate_report_pdf") > 0


def test_retention_expiry_math():
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    old = now - timedelta(days=100)
    recent = now - timedelta(days=1)
    assert _is_expired(old, 30, now) is True
    assert _is_expired(recent, 30, now) is False
    assert _is_expired(None, 30, now) is False


def test_s3_enabled_requires_all_creds(monkeypatch):
    from app.core import config

    monkeypatch.setenv("S3_BUCKET", "bucket")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIATEST")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test_p0.db")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    assert settings.s3_enabled is True

    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    assert settings.s3_enabled is False
    config.get_settings.cache_clear()


def test_export_zip_contains_json():
    from app.services.dsar_service import build_export_zip
    import zipfile
    import io

    raw = build_export_zip({"exported_at": "now", "sessions": []})
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        assert "export.json" in names
        assert "README.txt" in names
