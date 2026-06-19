import logging
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


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
    if not settings.SMTP_EMAIL or not settings.SMTP_PASSWORD:
        logger.warning("[EMAIL FALLBACK] SMTP not configured.")
        logger.warning(f"[EMAIL FALLBACK] To: {to_email}")
        logger.warning(f"[EMAIL FALLBACK] Subject: {subject}")
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

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
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


def send_verification_email(to_email: str, name: str, token: str):
    link = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={token}"

    print(f"\n[EMAIL] Verification link for {to_email}:")
    print(f"[EMAIL] {link}\n")

    subject = "Verify your SmartSkale account"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Verify your email</h2>
        <p>Hello {name},</p>
        <p>Please verify your email to activate your SmartSkale InterviewBot account.</p>
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
    _send_email(to_email, subject, html)


def send_invite_welcome_password_email(to_email: str, name: str, token: str) -> bool:
    """Send invite candidates a link to set their password after auto-registration."""
    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"

    print(f"\n[EMAIL] Invite welcome / set-password link for {to_email}:")
    print(f"[EMAIL] {link}\n")

    subject = "Your interview account is ready — set your password"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Welcome to SmartSkale</h2>
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
    return _send_email(to_email, subject, html)


def send_password_reset_email(to_email: str, name: str, token: str):
    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"

    print(f"\n[EMAIL] Password reset link for {to_email}:")
    print(f"[EMAIL] {link}\n")

    subject = "Reset your SmartSkale password"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #333;">Reset your password</h2>
        <p>Hello {name},</p>
        <p>You requested to reset your SmartSkale password.</p>
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
    _send_email(to_email, subject, html)


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
            You can also view your results and recording when you log back into SmartSkale InterviewBot.
        </p>
    </div>
    """

    print(f"\n[EMAIL] Interview report for {to_email} ({role_title})\n")

    return _send_email_with_attachment(
        to_email,
        subject,
        html,
        attachment_bytes=pdf_bytes,
        attachment_filename=pdf_filename,
    )
