import logging
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


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
    if not settings.email_configured:
        logger.warning(
            "[EMAIL FALLBACK] SMTP not configured (SMTP_EMAIL / SMTP_PASSWORD empty)."
        )
        logger.warning(f"[EMAIL FALLBACK] To: {to_email} | Subject: {subject}")
        return False

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_EMAIL
        msg["To"] = to_email

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

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(
                settings.SMTP_EMAIL.strip(),
                settings.SMTP_PASSWORD.strip(),
            )
            server.sendmail(
                settings.SMTP_EMAIL.strip(),
                to_email.strip(),
                msg.as_string(),
            )

        logger.info(f"[EMAIL] Sent successfully to {to_email}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"[EMAIL] Auth failed: {e}")
        logger.error("[EMAIL] Check: 1) Gmail App Password (not normal password)")
        logger.error("[EMAIL] Check: 2) 2FA enabled on Gmail account")
        logger.error("[EMAIL] Check: 3) No spaces in SMTP_PASSWORD in .env")
        logger.warning(f"[EMAIL FALLBACK] To: {to_email} | Subject: {subject}")
        return False

    except Exception as e:
        logger.error(f"[EMAIL] Failed to send: {e}")
        logger.warning(f"[EMAIL FALLBACK] To: {to_email} | Subject: {subject}")
        return False


def send_verification_email(to_email: str, name: str, token: str) -> str:
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
    return link


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


def send_password_reset_email(to_email: str, name: str, token: str) -> str:
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
    return link


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
    """Email the candidate their personal interview PDF report."""
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
            You can also view your results and recording when you log back into {settings.APP_NAME}.
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
