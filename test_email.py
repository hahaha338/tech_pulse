import os
os.environ["TECHPULSE_SMTP_PASSWORD"] = "YOUR_QQ_SMTP_AUTH_CODE"

from utils.config import load_config
from notifier import send_notification

config = load_config()
send_notification("TechPulse 测试邮件：邮件推送配置成功！", config)
print("发送完成，请检查 QQ 邮箱收件箱。")
