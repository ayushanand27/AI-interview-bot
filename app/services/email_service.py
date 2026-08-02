import logging
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)

# Last SMTP failure reason for API callers (never includes secrets).
_last_delivery_error: str | None = None


def get_last_email_delivery_error() -> str | None:
    return _last_delivery_error


def smtp_delivery_hint(*, any_failed: bool) -> str | None:
    """Short recruiter-facing note when invite emails fail."""
    if not any_failed:
        return None
    if not settings.email_configured:
        return (
            "SMTP is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_EMAIL, and "
            "SMTP_PASSWORD (Gmail App Password) in .env, then restart the backend."
        )
    if _last_delivery_error:
        return _last_delivery_error
    return "Email delivery failed. Check SMTP credentials and server logs."


def _log_console_fallback(kind: str, to_email: str, link: str | None = None) -> None:
    """Log a usable recovery path in non-prod; avoid printing tokens in production."""
    if settings.is_production:
        logger.error(
            "[EMAIL] %s not delivered to %s — SMTP missing or send failed. "
            "Set SMTP_EMAIL + SMTP_PASSWORD (and SMTP_HOST/SMTP_PORT) in .env, "
            "then restart PM2. Check /api/v1/status email_configured.",
            kind,
            to_email,
        )
        return
    if link:
        logger.warning("[EMAIL FALLBACK] %s for %s: %s", kind, to_email, link)
        print(f"\n[EMAIL] {kind} for {to_email}:")
        print(f"[EMAIL] {link}\n")
    else:
        logger.warning("[EMAIL FALLBACK] %s for %s (see subject/body in logs)", kind, to_email)


def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    return _send_email_with_attachment(
        to_email,
        subject,
        html_body,
        attachment_bytes=None,
        attachment_filename=None,
    )


def _send_email_with_attachment(
    to_email: str,
    subject: str,
    html_body: str,
    *,
    attachment_bytes: bytes | None,
    attachment_filename: str | None,
) -> bool:
    global _last_delivery_error

    if not settings.email_configured:
        _last_delivery_error = (
            "SMTP is not configured (SMTP_EMAIL / SMTP_PASSWORD empty)."
        )
        logger.warning("[EMAIL FALLBACK] %s", _last_delivery_error)
        logger.warning("[EMAIL FALLBACK] To: %s | Subject: %s", to_email, subject)
        return False

    try:
        from_addr = settings.SMTP_EMAIL.strip()
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_email.strip()

        msg.attach(MIMEText(html_body, "html"))

        if attachment_bytes and attachment_filename:
            attachment = MIMEApplication(attachment_bytes, _subtype="pdf")
            attachment.add_header(
                "Content-Disposition",
                "attachment",
                filename=attachment_filename,
            )
            msg.attach(attachment)

        context = ssl.create_default_context()
        host = settings.SMTP_HOST.strip()
        port = int(settings.SMTP_PORT)

        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(from_addr, settings.SMTP_PASSWORD.strip())
            server.sendmail(from_addr, [to_email.strip()], msg.as_string())

        _last_delivery_error = None
        logger.info("[EMAIL] Sent successfully to %s", to_email)
        return True

    except smtplib.SMTPAuthenticationError as e:
        _last_delivery_error = (
            "SMTP authentication failed. Use a Gmail App Password (not your normal "
            "password), ensure 2FA is enabled, and remove spaces from SMTP_PASSWORD."
        )
        logger.error("[EMAIL] Auth failed: %s", e)
        logger.error("[EMAIL] Check: 1) Gmail App Password (not normal password)")
        logger.error("[EMAIL] Check: 2) 2FA enabled on Gmail account")
        logger.error("[EMAIL] Check: 3) No spaces in SMTP_PASSWORD in .env")
        logger.warning("[EMAIL FALLBACK] To: %s | Subject: %s", to_email, subject)
        return False

    except Exception as e:
        _last_delivery_error = f"SMTP send failed: {type(e).__name__}"
        logger.error("[EMAIL] Failed to send: %s", e)
        logger.warning("[EMAIL FALLBACK] To: %s | Subject: %s", to_email, subject)
        return False


def send_verification_email(to_email: str, name: str, token: str) -> tuple[str, bool]:
    """Send verification email. Returns (link, delivered)."""
    link = f"{settings.effective_frontend_url}/verify-email?token={token}"

    subject = f"Verify your {settings.APP_NAME} account"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Verify your email</h2>
        <p>Hello {name},</p>
        <p>Please verify your email to activate your {settings.APP_NAME} account.</p>
        <a href="{link}"
           style="background: #4F46E5; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 6px; display: inline-block;">
            Verify Email
        </a>
        <p style="margin-top: 16px; color: #666; font-size: 14px;">
            Or copy this link: {link}
        </p>
        <p style="color: #666; font-size: 14px;">
            This link expires in 24 hours.
        </p>
    </div>
    """
    sent = _send_email(to_email, subject, html)
    if not sent:
        _log_console_fallback("Verification link", to_email, link)
    return link, sent


def send_invite_welcome_password_email(to_email: str, name: str, token: str) -> bool:
    """Send invite candidates a link to set their password after auto-registration."""
    link = f"{settings.effective_frontend_url}/reset-password?token={token}"

    subject = "Your interview account is ready — set your password"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Welcome to {settings.APP_NAME}</h2>
        <p>Hello {name},</p>
        <p>
            Your interview account has been created. Use the link below to set a password
            so you can log back in later to view your results.
        </p>
        <a href="{link}"
           style="background: #4F46E5; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 6px; display: inline-block;">
            Set your password
        </a>
        <p style="margin-top: 16px; color: #666; font-size: 14px;">
            Or copy this link: {link}
        </p>
        <p style="color: #666; font-size: 14px;">
            This link expires in 24 hours.
        </p>
    </div>
    """
    sent = _send_email(to_email, subject, html)
    if not sent:
        _log_console_fallback("Invite set-password link", to_email, link)
    return sent


def send_assessment_invite_email(
    to_email: str,
    *,
    invite_url: str,
    role_preview: str,
    recruiter_note: str | None = None,
) -> bool:
    """Send a candidate/institution the assessment invite link (recruiter-initiated)."""
    note_html = ""
    if recruiter_note and recruiter_note.strip():
        safe = (
            recruiter_note.strip()
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        note_html = f'<p style="margin-top: 12px; color: #444;">{safe}</p>'

    subject = f"You're invited to take an assessment — {role_preview}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Assessment invitation</h2>
        <p>Hello,</p>
        <p>
            You have been invited to complete an assessment for
            <strong>{role_preview}</strong> on {settings.APP_NAME}.
        </p>
        {note_html}
        <a href="{invite_url}"
           style="background: #0d9488; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 6px; display: inline-block;
                  margin-top: 8px;">
            Open assessment invite
        </a>
        <p style="margin-top: 16px; color: #666; font-size: 14px;">
            Or copy this link: {invite_url}
        </p>
        <p style="color: #666; font-size: 14px;">
            Please complete the assessment before the invite expires.
        </p>
    </div>
    """
    sent = _send_email(to_email, subject, html)
    if not sent:
        _log_console_fallback("Assessment invite link", to_email, invite_url)
    return sent


def send_live_interview_invite_email(
    to_email: str,
    *,
    candidate_name: str,
    room_title: str,
    live_url: str,
    meet_url: str | None = None,
    recruiter_note: str | None = None,
) -> bool:
    """Email candidate the live coding room link (+ optional Meet/Zoom)."""
    safe_name = (candidate_name or "there").strip() or "there"
    note_html = ""
    if recruiter_note and recruiter_note.strip():
        safe = (
            recruiter_note.strip()
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        note_html = f'<p style="margin-top: 12px; color: #444;">{safe}</p>'

    meet_html = ""
    if meet_url and meet_url.strip():
        meet = meet_url.strip()
        meet_html = f"""
        <p style="margin-top: 16px;">
          <strong>Video call:</strong>
          <a href="{meet}">{meet}</a>
        </p>
        """

    subject = f"Live interview invitation — {room_title}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Live interview invitation</h2>
        <p>Hello {safe_name},</p>
        <p>
            You are invited to a live technical interview
            (<strong>{room_title}</strong>) on {settings.APP_NAME}.
        </p>
        {note_html}
        {meet_html}
        <a href="{live_url}"
           style="background: #0d9488; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 6px; display: inline-block;
                  margin-top: 8px;">
            Join live coding room
        </a>
        <p style="margin-top: 16px; color: #666; font-size: 14px;">
            Or copy this link: {live_url}
        </p>
        <p style="color: #666; font-size: 14px;">
            Join a few minutes early. Use a desktop browser with a stable connection.
        </p>
    </div>
    """
    sent = _send_email(to_email, subject, html)
    if not sent:
        _log_console_fallback("Live interview invite", to_email, live_url)
    return sent


def send_password_reset_email(to_email: str, name: str, token: str) -> tuple[str, bool]:
    """Send password reset email. Returns (link, delivered)."""
    link = f"{settings.effective_frontend_url}/reset-password?token={token}"

    subject = f"Reset your {settings.APP_NAME} password"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Reset your password</h2>
        <p>Hello {name},</p>
        <p>You requested to reset your {settings.APP_NAME} password.</p>
        <a href="{link}"
           style="background: #4F46E5; color: white; padding: 12px 24px;
                  text-decoration: none; border-radius: 6px; display: inline-block;">
            Reset Password
        </a>
        <p style="margin-top: 16px; color: #666; font-size: 14px;">
            Or copy this link: {link}
        </p>
        <p style="color: #666; font-size: 14px;">
            This link expires in 1 hour.
        </p>
    </div>
    """
    sent = _send_email(to_email, subject, html)
    if not sent:
        _log_console_fallback("Password reset link", to_email, link)
        if not settings.is_production:
            logger.warning(
                "[EMAIL] Password reset SMTP send failed — use console/UI link in local dev."
            )
    return link, sent


def _format_integrity_level(integrity_level: str | None) -> str:
    if not integrity_level:
        return "Clean"
    return integrity_level.replace("_", " ").title()


def send_interview_report_email(
    to_email: str,
    name: str,
    *,
    role_title: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    overall_score: float | None = None,
    integrity_level: str | None = None,
) -> bool:
    """Email the candidate their personal interview PDF report (open practice only)."""
    subject = f"Your Interview Report - {role_title}"

    score_line = ""
    if overall_score is not None:
        score_line = f"<p><strong>Overall score:</strong> {overall_score} / 100</p>"

    integrity_line = (
        f"<p><strong>Integrity level:</strong> {_format_integrity_level(integrity_level)}</p>"
    )

    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Thank you for completing your interview</h2>
        <p>Hello {name},</p>
        <p>
            Your interview report for <strong>{role_title}</strong> is attached to this email.
        </p>
        {score_line}
        {integrity_line}
        <p style="color: #666; font-size: 14px;">
            You can also view your results when you log back into {settings.APP_NAME}.
        </p>
    </div>
    """

    sent = _send_email_with_attachment(
        to_email,
        subject,
        html,
        attachment_bytes=pdf_bytes,
        attachment_filename=pdf_filename,
    )
    if not sent:
        _log_console_fallback(f"Interview report ({role_title})", to_email, link=None)
    return sent


def send_recruiter_assessment_report_email(
    to_email: str,
    recruiter_name: str,
    *,
    candidate_name: str,
    role_title: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    overall_score: float | None = None,
    integrity_level: str | None = None,
) -> bool:
    """Email the recruiter the full assessment report after an invite interview."""
    subject = f"Assessment complete: {candidate_name} — {role_title}"
    score_line = ""
    if overall_score is not None:
        score_line = f"<p><strong>Overall score:</strong> {overall_score} / 100</p>"
    integrity_line = (
        f"<p><strong>Integrity level:</strong> {_format_integrity_level(integrity_level)}</p>"
    )
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Candidate assessment completed</h2>
        <p>Hello {recruiter_name},</p>
        <p>
            <strong>{candidate_name}</strong> completed the assessment for
            <strong>{role_title}</strong>. The full report is attached.
        </p>
        {score_line}
        {integrity_line}
        <p style="color: #666; font-size: 14px;">
            Open the recruiter dashboard to review the transcript, proctoring signals,
            and session recording (available immediately after a successful upload at
            interview end — usually within a few seconds).
        </p>
    </div>
    """
    sent = _send_email_with_attachment(
        to_email,
        subject,
        html,
        attachment_bytes=pdf_bytes,
        attachment_filename=pdf_filename,
    )
    if not sent:
        _log_console_fallback(f"Recruiter report ({role_title})", to_email, link=None)
    return sent
