from __future__ import annotations

import json
import mimetypes
import socket
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from auth import AuthError, AuthService
from chat_service import ChatService
from config import BASE_DIR, settings
from integrations import QQBotAdapter, handle_wechat_message, verify_wechat_signature
from llm_client import LLMClient
from storage import ChatStorage


STATIC_DIR = BASE_DIR / "static"
storage = ChatStorage(settings.data_dir / "chat.db")
chat_service = ChatService(storage, LLMClient(), settings.history_limit)
auth_service = AuthService(storage)
qq_adapter = QQBotAdapter(chat_service)


class CalebRequestHandler(BaseHTTPRequestHandler):
    server_version = "CalebChat/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def _session_token(self) -> str:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return ""
        morsel = cookie.get("caleb_session")
        return morsel.value if morsel else ""

    def _current_user(self) -> dict | None:
        return auth_service.authenticate(self._session_token())

    def _set_session_cookie(self, token: str) -> None:
        secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
        parts = [
            "caleb_session=" + token,
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
            "Max-Age=" + str(60 * 60 * 24 * 180),
        ]
        if secure:
            parts.append("Secure")
        self.send_header("Set-Cookie", "; ".join(parts))

    def _clear_session_cookie(self) -> None:
        secure = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
        value = "caleb_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        if secure:
            value += "; Secure"
        self.send_header("Set-Cookie", value)

    def _read_body(self, limit: int = 1_048_576) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return b""
        if length > limit:
            raise ValueError("request body too large")
        return self.rfile.read(length)

    def _send_bytes(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json_payload(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, data, "application/json; charset=utf-8")

    def _send_empty(self, status: int = 204) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json_body(self) -> dict:
        raw = self._read_body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        if relative.startswith("static/"):
            relative = relative[len("static/"):]
        candidate = (STATIC_DIR / relative).resolve()
        static_root = STATIC_DIR.resolve()
        if static_root not in candidate.parents and candidate != static_root:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        if not candidate.exists() or not candidate.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        content_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self._send_bytes(HTTPStatus.OK, candidate.read_bytes(), content_type)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "provider": settings.provider,
                    "model": settings.model,
                    "wechat_configured": bool(settings.wechat_token),
                    "qq_configured": bool(settings.qq_app_id and settings.qq_client_secret),
                },
            )
            return

        if parsed.path == "/api/me":
            user = self._current_user()
            if not user:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"authenticated": False})
                return
            self._send_json(HTTPStatus.OK, {"authenticated": True, "user": user})
            return

        if parsed.path == "/api/history":
            user = self._current_user()
            if not user:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "login required"})
                return
            limit = int(parse_qs(parsed.query).get("limit", ["30"])[0])
            self._send_json(
                HTTPStatus.OK,
                {"history": storage.get_history(user["id"], max(1, min(limit, 60)))},
            )
            return

        if parsed.path == "/api/persona":
            self._send_json(
                HTTPStatus.OK,
                {
                    "name": "夏以昼 / Caleb",
                    "role": "远空舰队执舰官 · DAA战斗机飞行员 · 引力控制 Evol",
                    "birthday": "06-13",
                    "relationship": "主控的没有血缘关系的哥哥与长期亲密对象",
                },
            )
            return

        if parsed.path == "/webhooks/wechat":
            query = parse_qs(parsed.query)
            signature = query.get("signature", [""])[0]
            timestamp = query.get("timestamp", [""])[0]
            nonce = query.get("nonce", [""])[0]
            echostr = query.get("echostr", [""])[0]
            if verify_wechat_signature(signature, timestamp, nonce):
                self._send_bytes(HTTPStatus.OK, echostr.encode("utf-8"), "text/plain; charset=utf-8")
            else:
                self._send_bytes(HTTPStatus.FORBIDDEN, b"invalid signature", "text/plain; charset=utf-8")
            return

        if parsed.path == "/favicon.ico":
            self._send_empty()
            return

        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/register":
                body = self._json_body()
                token, user = auth_service.register(
                    str(body.get("username") or ""),
                    str(body.get("password") or ""),
                    str(body.get("display_name") or ""),
                )
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._set_session_cookie(token)
                self._send_json_payload({"ok": True, "user": user})
                return

            if parsed.path == "/api/login":
                body = self._json_body()
                token, user = auth_service.login(
                    str(body.get("username") or ""),
                    str(body.get("password") or ""),
                )
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._set_session_cookie(token)
                self._send_json_payload({"ok": True, "user": user})
                return

            if parsed.path == "/api/logout":
                auth_service.logout(self._session_token())
                self.send_response(HTTPStatus.NO_CONTENT)
                self._clear_session_cookie()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if parsed.path == "/api/chat":
                current_user = self._current_user()
                if not current_user:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "login required"})
                    return
                body = self._json_body()
                message = str(body.get("message") or "")
                platform = str(body.get("platform") or "web")
                result = chat_service.reply(current_user["id"], message, platform)
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "reply": result.text,
                        "provider": result.provider,
                        "model": result.model,
                        "warning": result.warning,
                    },
                )
                return

            if parsed.path == "/api/reset":
                current_user = self._current_user()
                if not current_user:
                    self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "login required"})
                    return
                chat_service.reset(current_user["id"])
                self._send_json(HTTPStatus.OK, {"ok": True})
                return

            if parsed.path == "/webhooks/wechat":
                raw = self._read_body()
                reply_xml = handle_wechat_message(raw, chat_service)
                self._send_bytes(HTTPStatus.OK, reply_xml, "application/xml; charset=utf-8")
                return

            if parsed.path == "/webhooks/qq":
                raw = self._read_body()
                headers = {key.lower(): value for key, value in self.headers.items()}
                status, payload = qq_adapter.handle_webhook(raw, headers)
                if status == HTTPStatus.NO_CONTENT:
                    self._send_empty(status)
                else:
                    self._send_json(status, payload)
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except AuthError as error:
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": str(error)})
        except ValueError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:
            print("Request error:", repr(error))
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal server error"})

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()


def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
        sock.close()
        return address
    except Exception:
        return "127.0.0.1"


def main() -> None:
    server = ThreadingHTTPServer((settings.host, settings.port), CalebRequestHandler)
    print("")
    print("Caleb AI Chat is running.")
    print(f"Computer: http://127.0.0.1:{settings.port}")
    print(f"LAN/phone: http://{local_ip()}:{settings.port}")
    print(f"Provider: {settings.provider} / {settings.model}")
    print("Press Ctrl+C to stop.")
    print("")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
