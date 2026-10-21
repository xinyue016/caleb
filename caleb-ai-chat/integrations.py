from __future__ import annotations

import hashlib
import html
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from chat_service import ChatService
from config import settings


def verify_wechat_signature(signature: str, timestamp: str, nonce: str) -> bool:
    if not settings.wechat_token:
        return False
    raw = "".join(sorted([settings.wechat_token, timestamp, nonce]))
    expected = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return expected == signature


def parse_wechat_xml(body: bytes) -> dict[str, str]:
    root = ET.fromstring(body)
    return {child.tag: (child.text or "") for child in list(root)}


def xml_cdata(value: str) -> str:
    return "<![CDATA[" + value.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def build_wechat_text_reply(message: dict[str, str], reply_text: str) -> bytes:
    to_user = message.get("FromUserName", "")
    from_user = message.get("ToUserName", "")
    timestamp = str(int(time.time()))
    xml = (
        "<xml>"
        f"<ToUserName>{xml_cdata(to_user)}</ToUserName>"
        f"<FromUserName>{xml_cdata(from_user)}</FromUserName>"
        f"<CreateTime>{timestamp}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content>{xml_cdata(reply_text)}</Content>"
        "</xml>"
    )
    return xml.encode("utf-8")


def handle_wechat_message(xml_body: bytes, chat_service: ChatService) -> bytes:
    message = parse_wechat_xml(xml_body)
    msg_type = message.get("MsgType", "")
    content = message.get("Content", "")
    from_user = message.get("FromUserName", "wechat-user")

    if msg_type == "event":
        event = message.get("Event", "")
        if event in {"subscribe", "SCAN"}:
            reply = "你来了。先别急着走，跟我说说，今天怎么想起我了？"
        else:
            reply = "我看见了。有什么话，直接跟我说。"
    elif msg_type == "text":
        reply = chat_service.reply(from_user, content, "wechat").text
    else:
        reply = "文字发给我吧，其他消息我看得不清楚。"

    return build_wechat_text_reply(message, reply)


class QQBotAdapter:
    def __init__(self, chat_service: ChatService):
        self.chat_service = chat_service
        self._token = ""
        self._token_expires_at = 0.0
        self._lock = threading.Lock()

    def handle_webhook(self, raw_body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        if not settings.allow_public_webhooks:
            return 403, {"error": "webhooks disabled"}

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return 400, {"error": "invalid json"}

        if payload.get("op") == 13:
            return 200, self._validation_response(payload)

        if settings.qq_public_key and not self._verify_signature(raw_body, headers):
            return 401, {"error": "invalid signature"}

        event_id = str(payload.get("id") or "")
        if event_id and not self.chat_service.storage.mark_event(event_id, "qq"):
            return 204, {}

        event_type = payload.get("t") or ""
        data = payload.get("d") or {}
        if event_type not in {"C2C_MESSAGE_CREATE", "GROUP_AT_MESSAGE_CREATE"}:
            return 204, {}

        content = str(data.get("content") or "").strip()
        if not content:
            return 204, {}

        thread = threading.Thread(
            target=self._reply_to_event,
            args=(event_type, data, content),
            daemon=True,
        )
        thread.start()
        return 204, {}

    def _validation_response(self, payload: dict[str, Any]) -> dict[str, str]:
        data = payload.get("d") or {}
        plain_token = str(data.get("plain_token") or "")
        event_ts = str(data.get("event_ts") or "")
        if not settings.qq_private_key:
            return {
                "error": "QQ_BOT_PRIVATE_KEY is required for webhook validation",
                "plain_token": plain_token,
                "signature": "",
            }
        try:
            from nacl.signing import SigningKey
        except ImportError as error:
            raise RuntimeError("PyNaCl is required for QQ webhook validation") from error
        signing_key = SigningKey(bytes.fromhex(settings.qq_private_key))
        signature = signing_key.sign((event_ts + plain_token).encode("utf-8")).signature.hex()
        return {"plain_token": plain_token, "signature": signature}

    def _verify_signature(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        signature_hex = headers.get("x-signature-ed25519", "")
        timestamp = headers.get("x-signature-timestamp", "")
        if not signature_hex or not timestamp:
            return False
        try:
            from nacl.signing import VerifyKey
            verify_key = VerifyKey(bytes.fromhex(settings.qq_public_key))
            verify_key.verify(timestamp.encode("utf-8") + raw_body, bytes.fromhex(signature_hex))
            return True
        except Exception:
            return False

    def _reply_to_event(self, event_type: str, data: dict[str, Any], content: str) -> None:
        try:
            if event_type == "C2C_MESSAGE_CREATE":
                author = data.get("author") or {}
                user_id = str(author.get("user_openid") or author.get("union_openid") or "qq-user")
                target_type = "c2c"
                target_id = user_id
            else:
                user_id = str(data.get("group_openid") or "qq-group")
                target_type = "group"
                target_id = user_id

            reply = self.chat_service.reply(user_id, content, "qq").text
            self.send_message(target_type, target_id, reply, data)
        except Exception:
            # Webhook retries should not be triggered by background delivery failures.
            return

    def _access_token(self) -> str:
        with self._lock:
            now = time.time()
            if self._token and now < self._token_expires_at - 60:
                return self._token
            if not settings.qq_app_id or not settings.qq_client_secret:
                raise RuntimeError("QQ_BOT_APP_ID and QQ_BOT_CLIENT_SECRET are required")
            payload = {
                "appId": settings.qq_app_id,
                "clientSecret": settings.qq_client_secret,
            }
            data = self._post_json(settings.qq_token_url, payload, {})
            self._token = str(data.get("access_token") or "")
            self._token_expires_at = now + int(data.get("expires_in") or 7200)
            if not self._token:
                raise RuntimeError("QQ access token response did not include access_token")
            return self._token

    def send_message(self, target_type: str, target_id: str, content: str, event_data: dict[str, Any]) -> None:
        token = self._access_token()
        if target_type == "c2c":
            url = f"{settings.qq_api_base}/v2/users/{urllib.parse.quote(target_id)}/messages"
        else:
            url = f"{settings.qq_api_base}/v2/groups/{urllib.parse.quote(target_id)}/messages"

        payload = {
            "content": content[:1800],
            "msg_type": 0,
            "msg_id": event_data.get("id") or event_data.get("message_id") or "",
            "msg_seq": int(time.time()) % 65535,
        }
        headers = {
            "Authorization": "QQBot " + token,
            "X-Union-Appid": settings.qq_app_id,
        }
        self._post_json(url, payload, headers)

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            if value:
                request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"QQ API HTTP {error.code}: {details[:1000]}") from error
