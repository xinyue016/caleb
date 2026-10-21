from __future__ import annotations

import json
import random
import urllib.error
import urllib.request
from dataclasses import dataclass

from config import settings
from persona import get_system_prompt


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str


class LLMClient:
    def __init__(self):
        self.provider = settings.provider
        self.model = settings.model
        self.api_key = settings.api_key
        self.base_url = settings.base_url

    def generate(self, messages: list[dict[str, str]], platform: str = "web") -> LLMResult:
        recent_assistant = [
            item.get("content", "")
            for item in messages
            if item.get("role") == "assistant" and item.get("content")
        ][-4:]
        system_prompt = get_system_prompt(platform, recent_assistant)
        if self.provider == "mock":
            return LLMResult(mock_reply(messages, platform), "mock", "persona-rules")
        if self.provider in {"openai", "responses"}:
            return LLMResult(self._openai_responses(system_prompt, messages), self.provider, self.model)
        if self.provider in {"openai_compatible", "compatible", "chat_completions"}:
            return LLMResult(self._chat_completions(system_prompt, messages), self.provider, self.model)
        if self.provider == "ollama":
            return LLMResult(self._ollama_chat(system_prompt, messages), self.provider, self.model)
        raise LLMError("Unknown CALEB_PROVIDER: " + self.provider)

    def _request_json(self, url: str, payload: dict, headers: dict[str, str]) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            if value:
                request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=settings.request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise LLMError(f"Provider HTTP {error.code}: {details[:1000]}") from error
        except Exception as error:
            raise LLMError(f"Provider request failed: {error}") from error

    def _openai_responses(self, system_prompt: str, messages: list[dict[str, str]]) -> str:
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is required when CALEB_PROVIDER=openai")
        payload = {
            "model": self.model,
            "instructions": system_prompt,
            "input": [
                {"role": item["role"], "content": item["content"]}
                for item in messages
                if item.get("role") in {"user", "assistant"}
            ],
            "temperature": settings.temperature,
            "max_output_tokens": settings.max_output_tokens,
        }
        data = self._request_json(
            self.base_url + "/responses",
            payload,
            {"Authorization": "Bearer " + self.api_key},
        )
        chunks: list[str] = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(content["text"])
        text = "\n".join(chunks).strip()
        if not text:
            raise LLMError("Empty response from OpenAI Responses API")
        return text

    def _chat_completions(self, system_prompt: str, messages: list[dict[str, str]]) -> str:
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY is required for OpenAI-compatible providers")
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "temperature": settings.temperature,
            "max_tokens": settings.max_output_tokens,
        }
        data = self._request_json(
            self.base_url + "/chat/completions",
            payload,
            {"Authorization": "Bearer " + self.api_key},
        )
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
        if not text:
            raise LLMError("Empty response from chat-completions provider")
        return text

    def _ollama_chat(self, system_prompt: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "options": {"temperature": settings.temperature},
        }
        data = self._request_json(self.base_url + "/api/chat", payload, {})
        text = (data.get("message") or {}).get("content", "").strip()
        if not text:
            raise LLMError("Empty response from Ollama")
        return text


def mock_reply(messages: list[dict[str, str]], platform: str = "web") -> str:
    text = ""
    for item in reversed(messages):
        if item.get("role") == "user":
            text = item.get("content", "").strip()
            break

    recent_assistant = {
        item.get("content", "").strip()
        for item in messages
        if item.get("role") == "assistant"
    }

    def choose(options: list[str]) -> str:
        fresh = [option for option in options if option not in recent_assistant]
        if not fresh:
            fresh = options
        seed = len(text) + sum(ord(char) for char in text[:80]) + len(messages)
        return fresh[seed % len(fresh)]

    lower = text.lower()

    if any(word in text for word in ("你好", "嗨", "在吗", "hello", "hi")):
        return choose([
            "刚忙完。你看起来像是有话要说。",
            "在。你说，我先听着。",
            "怎么，今天这么难得主动？",
            "我还以为你又要隔半天才回我。",
        ])

    if any(word in text for word in ("不需要你", "不用你管", "别管我", "不需要哥哥")):
        return choose([
            "再说一次。",
            "不需要我？你确定？",
            "行。那你先看着我，把这句话再说完整。",
            "不需要我？好啊，那你需要什么？我都可以答应。你想要回临空，我们就回临空，你想回到从前，我们就把老宅翻修，一起住过去。一座房子不够，那就给你建一座迷宫，我会在里面给你准备最好的一切，把它建成世界上最漂亮的花园，有我陪着，以后他们就再也找不到你了。",
            "这句话我可以当没听见。下一句想好了再说。",
        ])

    if any(word in text for word in ("受伤", "流血", "伤口", "好疼", "很疼", "我能忍", "没事的", "不在乎")):
        return choose([
            "别动。先把伤处理了，剩下的话等下再说。",
            "你再说一遍没事。",
            "我没在跟你商量。坐下，把手给我。",
            "疼就出声，不要忍着。你还想瞒我到什么时候？",
            "先处理伤口。想挨训，等你不流血了再说。",
        ])

    if len(text) <= 16 and any(word in text for word in ("妹妹", "哥哥", "理我", "陪我", "无聊", "在吗")):
        return choose([
            "妹妹？妹妹。你终于舍得理我了？",
            "妹妹，忙完没有。回我一句也行。",
            "妹妹——你再说一声不理我，我就真过去了。",
            "妹妹，我数到三。算了，不数了，你回我。",
            "妹妹，别装没看见。我都叫你几声了。",
        ])

    if any(word in text for word in ("在做什么", "在干嘛", "忙什么", "做什么")):
        return choose([
            "刚把飞行记录整理完，手上还沾着模型胶。你那边呢？",
            "本来在检查航线，被你打断得刚刚好。",
            "什么都没做，正想着要不要找个人烦一烦。",
            "在修模型。少一个零件，暂时不想承认是我弄丢的。",
        ])

    if any(word in text for word in ("回不回家", "回家", "回来", "见面")):
        return choose([
            "想让我回去就直说。航班又不会笑你。",
            "回。你想吃什么，我顺路买。",
            "今天不行，明天可以。你先把时间留出来。",
            "可以回去。不过你最好不是只打算让我在门口站一会儿。",
        ])

    if any(word in text for word in ("飞机", "模型", "飞行")):
        return choose([
            "模型在桌上，机翼刚修好，别装没看见又开始碰。",
            "想听哪种？FY-26，还是那架只飞过两次的原型机。",
            "下次过来，我带你把它拼完。你负责找零件，我负责不让你弄坏。",
            "飞行没什么浪漫的。真到了上面，第一件事是想清怎么回来。",
        ])

    if any(word in text for word in ("资产", "工资", "钱", "兰博基尼", "浮岛")):
        return choose([
            "资产表没什么好看的。你真想知道，我从最无聊的一项开始念。",
            "那些数字是我的，不是拿来跟你炫耀的。你想看就看。",
            "兰博基尼是代步，模型才是我自己挑的。",
            "工资和权益都在账上。少盯着数字，先看你缺什么。",
        ])

    if any(word in text for word in ("想你了", "想你", "喜欢", "爱")):
        return choose([
            "嗯，听出来了。还有别的要说吗？",
            "这句话别发在屏幕上。见面再说。",
            "是吗。那你最好给我一个具体一点的想。",
            "我听见了。暂时先不拆穿你是不是又在哄我。",
        ])

    if any(word in text for word in ("难过", "不开心", "累", "烦", "哭", "生气", "对不起", "抱歉")):
        return choose([
            "嗯。你今天不太对。要不要先说最不想说的那部分？",
            "可以不说，但别一个人硬撑。先把位置发给我。",
            "我没打算劝你什么。就在这儿陪你坐会儿。",
            "先别道歉。把事情说清楚，剩下的交给我。",
        ])

    if platform == "wechat":
        return choose(["在，你说。", "刚回来，怎么了？", "别急，慢慢说。", "看到了。然后呢？"])
    if platform == "qq":
        return choose(["在。", "说吧，我听着。", "刚忙完，怎么了？", "嗯，然后？"])

    return choose([
        "嗯，我听着。然后呢？",
        "这句话我记住了。还有后半句吗？",
        "你这么说，我反而想见你了。",
        "好。你继续，我不打断。",
        "听起来不像没事。你在哪儿？",
    ])
