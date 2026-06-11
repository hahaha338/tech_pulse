import os
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict


def _send_email(content: str, channel_cfg: Dict[str, Any]) -> None:
    smtp_host = channel_cfg.get("smtp_host")
    smtp_port = int(channel_cfg.get("smtp_port", 587))
    sender = channel_cfg.get("from")
    recipients = channel_cfg.get("to", [])
    username = channel_cfg.get("username") or sender
    # Password: config field takes precedence, then env var TECHPULSE_SMTP_PASSWORD
    password = channel_cfg.get("password") or os.environ.get("TECHPULSE_SMTP_PASSWORD", "")

    if not smtp_host:
        raise ValueError("smtp_host is not configured.")
    if not sender:
        raise ValueError("Email sender is not configured.")
    if not recipients:
        raise ValueError("Email recipients are not configured.")

    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = "📡 TechPulse 技术追踪更新"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if password:
            smtp.login(username, password)
        smtp.sendmail(sender, recipients, msg.as_string())


def send_notification(report: str, config: Dict[str, Any], logger=None) -> None:
    """Send report to configured notification channels.

    Channel failures are logged but do not stop the whole job.
    """
    channels = config.get("notifier", {}).get("channels", [])

    enabled_channels = [ch for ch in channels if ch.get("enabled", False)]
    if not enabled_channels:
        if logger:
            logger.info("No notifier channel enabled. Report is archived only.")
        return

    for channel in enabled_channels:
        channel_type = channel.get("type")

        try:
            if channel_type == "email":
                _send_email(report, channel)
                if logger:
                    logger.info("Email notification sent")
            else:
                if logger:
                    logger.warning("Unknown notifier channel type: %s", channel_type)
        except Exception as exc:
            if logger:
                logger.warning("Failed to send %s notification: %s", channel_type, exc)