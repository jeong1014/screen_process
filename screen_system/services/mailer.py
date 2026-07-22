"""
발주 메일 발송 — settings 테이블에 저장된 SMTP 설정을 사용.

SMTP 미설정이어도 발주 요청 레코드 자체는 생성되어야 하므로,
전송 실패 시 예외를 던지지 않고 (False, 사유) 를 돌려준다.
"""

import smtplib
import ssl
from email.message import EmailMessage

from db import _get_setting


def _smtp_config(cur):
    return {
        "to":   (_get_setting(cur, "purchase_email_to", "") or "").strip(),
        "host": (_get_setting(cur, "smtp_host", "") or "").strip(),
        "port": int(_get_setting(cur, "smtp_port", "587") or "587"),
        "user": (_get_setting(cur, "smtp_user", "") or "").strip(),
        "pass": (_get_setting(cur, "smtp_pass", "") or ""),
        "from": (_get_setting(cur, "smtp_from", "") or "").strip(),
        "tls":  (_get_setting(cur, "smtp_tls", "starttls") or "starttls").strip(),
    }


def _send_purchase_email(cfg, subject, body):
    """SMTP設定があればメール送信。未設定なら送らず False を返す(依頼レコードは作られる)。"""
    if not cfg["to"] or not cfg["host"]:
        return False, "メール未設定(宛先/SMTPホスト)"
    sender = cfg["from"] or cfg["user"] or cfg["to"].split(",")[0]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = cfg["to"]
    msg.set_content(body)
    try:
        if cfg["tls"] == "ssl":
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx, timeout=15) as s:
                if cfg["user"]:
                    s.login(cfg["user"], cfg["pass"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as s:
                if cfg["tls"] == "starttls":
                    s.starttls(context=ssl.create_default_context())
                if cfg["user"]:
                    s.login(cfg["user"], cfg["pass"])
                s.send_message(msg)
        return True, "送信しました"
    except Exception as e:
        return False, f"送信失敗: {str(e).splitlines()[0]}"
