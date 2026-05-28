import logging
import smtplib
import socket
import ssl
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT_SECONDS = 30


def _ipv4_socket(host: str, port: int, timeout: float) -> socket.socket:
    """Open a TCP connection over IPv4 only.

    Docker/CapRover networks often have no IPv6 route; smtplib then fails with
    errno 101 (Network is unreachable) when the SMTP host has AAAA records.
    """
    last_err: OSError | None = None
    for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
        host, port, socket.AF_INET, socket.SOCK_STREAM
    ):
        sock = socket.socket(_family, _type, _proto)
        sock.settimeout(timeout)
        try:
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            last_err = exc
            sock.close()
    raise last_err or OSError(f"No IPv4 route to {host}:{port}")


def _smtp_client(host: str, port: int, *, use_tls: bool) -> smtplib.SMTP:
    """SMTP client connected over IPv4 (STARTTLS when use_tls is True)."""
    smtp = smtplib.SMTP(timeout=_SMTP_TIMEOUT_SECONDS)
    smtp.sock = _ipv4_socket(host, port, _SMTP_TIMEOUT_SECONDS)
    smtp.file = smtp.sock.makefile("rb")
    smtp.host = host
    smtp.port = port
    code, msg = smtp.getreply()
    if code != 220:
        smtp.close()
        raise smtplib.SMTPConnectError(code, msg)
    smtp.ehlo()
    if use_tls:
        context = ssl.create_default_context()
        smtp.starttls(context=context)
        smtp.ehlo()
    return smtp


def _smtp_ssl_client(host: str, port: int) -> smtplib.SMTP_SSL:
    """SMTP_SSL client connected over IPv4."""
    context = ssl.create_default_context()
    smtp = smtplib.SMTP_SSL(context=context, timeout=_SMTP_TIMEOUT_SECONDS)
    raw = _ipv4_socket(host, port, _SMTP_TIMEOUT_SECONDS)
    smtp.sock = context.wrap_socket(raw, server_hostname=host)
    smtp.file = smtp.sock.makefile("rb")
    smtp.host = host
    smtp.port = port
    code, msg = smtp.getreply()
    if code != 220:
        smtp.close()
        raise smtplib.SMTPConnectError(code, msg)
    smtp.ehlo()
    return smtp


class EmailDeliveryError(Exception):
    pass


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send_password_reset(self, *, to_email: str, reset_url: str) -> None:
        subject = f"Reset your {self.settings.app_name} password"
        body = (
            f"You requested a password reset for {self.settings.app_name}.\n\n"
            f"Open this link to set a new password (expires in "
            f"{self.settings.password_reset_token_hours} hours):\n\n"
            f"{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        )
        self._send(to_email=to_email, subject=subject, body=body)

    def _send(self, *, to_email: str, subject: str, body: str) -> None:
        if not self.settings.smtp_configured:
            logger.warning(
                "SMTP not configured; password reset link for %s: %s",
                to_email,
                body,
            )
            if self.settings.app_env == "development":
                return
            raise EmailDeliveryError(
                "Email is not configured. Set SMTP_HOST and SMTP_FROM in .env"
            )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.settings.smtp_from
        message["To"] = to_email
        message.set_content(body)

        host = self.settings.smtp_host
        port = self.settings.smtp_port
        server: smtplib.SMTP | None = None
        try:
            if self.settings.smtp_use_tls:
                server = _smtp_client(host, port, use_tls=True)
            else:
                server = _smtp_ssl_client(host, port)
            if self.settings.smtp_user:
                server.login(
                    self.settings.smtp_user,
                    self.settings.smtp_password,
                )
            server.send_message(message)
        except OSError as exc:
            logger.exception(
                "Failed to send email to %s via %s:%s", to_email, host, port
            )
            hint = (
                " (container may block outbound SMTP or lack IPv6; "
                "use port 587 with SMTP_USE_TLS=true)"
                if getattr(exc, "errno", None) == 101
                else ""
            )
            raise EmailDeliveryError(f"Failed to send email: {exc}{hint}") from exc
        except smtplib.SMTPException as exc:
            logger.exception(
                "SMTP error sending to %s via %s:%s", to_email, host, port
            )
            raise EmailDeliveryError(f"Failed to send email: {exc}") from exc
        finally:
            if server is not None:
                try:
                    server.quit()
                except smtplib.SMTPException:
                    server.close()
