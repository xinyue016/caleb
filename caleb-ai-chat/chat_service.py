from __future__ import annotations

from dataclasses import dataclass

from llm_client import LLMClient, LLMError, mock_reply
from storage import ChatStorage


@dataclass
class ChatReply:
    text: str
    provider: str
    model: str
    warning: str = ""


class ChatService:
    def __init__(self, storage: ChatStorage, llm: LLMClient, history_limit: int = 14):
        self.storage = storage
        self.llm = llm
        self.history_limit = history_limit

    def reply(self, user_id: str, message: str, platform: str = "web") -> ChatReply:
        message = (message or "").strip()
        if not message:
            return ChatReply("我在。你想说什么？", "system", "validation")
        if len(message) > 6000:
            message = message[:6000]

        history = self.storage.get_history(user_id, self.history_limit)
        history.append({"role": "user", "content": message})
        self.storage.add_message(user_id, platform, "user", message)

        warning = ""
        try:
            result = self.llm.generate(history, platform)
            text = result.text
            provider = result.provider
            model = result.model
        except LLMError as error:
            # Keep the bot usable even if the configured model is unavailable.
            text = mock_reply(history, platform)
            provider = "mock-fallback"
            model = "persona-rules"
            warning = str(error)

        self.storage.add_message(user_id, platform, "assistant", text)
        return ChatReply(text=text, provider=provider, model=model, warning=warning)

    def reset(self, user_id: str) -> None:
        self.storage.clear(user_id)
