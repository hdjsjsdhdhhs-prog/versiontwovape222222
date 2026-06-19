import html
import json
import urllib.request


def escape_html(value: str | None) -> str:
    return html.escape(value or "", quote=False)


def send_message(bot_token: str, chat_id: str | int, text: str) -> None:
    if not bot_token or not chat_id:
        return
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except OSError:
        return
