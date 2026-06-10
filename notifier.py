import os
import smtplib
from email.mime.text import MIMEText
from typing import Any, Dict

import requests


def _send_wecom(content: str, channel_cfg: Dict[str, Any]) -> None:
    webhook_url_env = channel_cfg.get("webhook_url_env", "WECOM_WEBHOOK_URL")
    webhook_url = os.environ.get(webhook_url_env)

    if not webhook_url:
        raise ValueError(f"Environment variable {webhook_url_env} is not set.")

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content,
        },
    }

    response = requests.post(webhook_url, json=payload, timeout=20)
    response.raise_for_status()


def _send_email(content: str, channel_cfg: Dict[str, Any]) -> None:
    smtp_host = channel_cfg.get("smtp_host")
    smtp_port = int(channel_cfg.get("smtp_port", 587))
    sender = channel_cfg.get("from")
    recipients = channel_cfg.get("to", [])

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
            if channel_type == "wecom":
                _send_wecom(report, channel)
                if logger:
                    logger.info("WeCom notification sent")
            elif channel_type == "email":
                _send_email(report, channel)
                if logger:
                    logger.info("Email notification sent")
            else:
                if logger:
                    logger.warning("Unknown notifier channel type: %s", channel_type)
        except Exception as exc:
            if logger:
                logger.warning("Failed to send %s notification: %s", channel_type, exc)