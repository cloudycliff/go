"""LLM explanations ("AI 老师说") through an OpenAI-compatible chat API (DeepSeek by default).

The model only gets the key point's facts (with IDs and their plain meaning), the marks, and the
child's age and rank. It never sees coordinates, the board or engine output, so it has nothing to
invent positions from. Its JSON answer is checked by verify.py; on failure it gets the violations
and one more try. Answers are cached in raw/<id>.json.gz by a hash of everything sent.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from . import narrate_template, verify
from .config import LLMConfig

PROMPT_VERSION = 3
# Facts kept for statistics but useless to a child (phase / category labels).
HIDDEN_FACTS = {"phase"}

SYSTEM = """你是一位耐心的围棋老师，正在给一个 {age} 岁、野狐 {rank} 的孩子讲他自己下的一盘棋里的一个关键点。

规则（必须遵守）：
1. 只能使用下面给出的“事实”，不能补充任何事实之外的内容；不确定就不说。
2. 每句话都要在 refs 里写上它用到的事实 ID（至少一个）。
3. 只能用标记称呼位置：✕（孩子下的位置）、A、B、▲、△、■、□。不能写坐标，也不要说“第几路”。
4. 数字只能用事实里出现过的数字，用阿拉伯数字写；不要出现百分号，也不要提胜率。
5. 只有引用了提子或棋块死活的事实时，才能说“死”“活”“吃”。
6. 不要用这些词：劫、征子、定式、先手、后手、双活、眼。
7. 对孩子说话，用“你”。写 3～5 句，每句不超过 30 个字。
8. 最后给一个 tip：下次遇到这种情况，先看什么。tip 也要写 refs，同样不超过 30 个字。

怎么讲得好：
- 不用把每条事实都讲一遍，挑最重要的 2～4 条，连成一段自然的话：先说发生了什么，再说为什么，最后说该怎么下。
- 像老师当面说话，不要写“等级是”“类别是”这种报表式的话。
- 语气温和、具体，可以鼓励，但不要夸张。
- 只讲这一手当时的局面。不要推测后面的棋（比如“还来得及”“还有机会补上”），也不要猜孩子的心态或性格（比如“太急了”“粗心”）。

只输出 json，格式如下：
{{"sentences": [{{"text": "你下了✕以后，对方可以吃掉▲这4颗子。", "refs": ["f2"]}}],
 "tip": {{"text": "被叫吃时先数一数气，看能不能逃。", "refs": ["f3"]}}}}"""

KIND_ZH = {
    "mistake": "错误：孩子这手亏了",
    "missed_punish": "没惩罚对方：对方上一手犯了错，孩子没有抓住",
    "missed_urgent": "漏掉急所：同一个急所，孩子好几次都没有下",
    "good": "好棋：孩子下出了强的人才会下的一手，要表扬",
}


class LLMError(RuntimeError):
    pass


def payload(kp: dict) -> dict:
    """What the model is told about one key point."""
    facts = shown_facts(kp)
    return {
        "类型": KIND_ZH.get(kp["kind"], kp["kind"]),
        "标记": sorted({m["label"] for m in kp["marks"] if m.get("label")}),
        "可下点": [c for c in kp.get("candidates", []) if c.get("label")],
        "事实": [{**f, "含义": narrate_template.describe(f)} for f in facts],
    }


def messages(kp: dict, age: int, rank: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM.format(age=age, rank=rank)},
        {"role": "user", "content": json.dumps(payload(kp), ensure_ascii=False)},
    ]


def cache_key(cfg: LLMConfig, msgs: list[dict]) -> str:
    text = json.dumps([PROMPT_VERSION, cfg.provider, cfg.model, cfg.thinking, msgs], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


class Client:
    def __init__(self, cfg: LLMConfig, api_key: str, timeout: float = 90.0) -> None:
        self.cfg, self.api_key, self.timeout = cfg, api_key, timeout

    @classmethod
    def from_env(cls, cfg: LLMConfig) -> "Client | None":
        key = os.environ.get(cfg.api_key_env, "").strip()
        if not key and os.name == "nt":
            # A user variable set after this terminal started is only in the registry.
            try:
                import winreg

                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
                    key = str(winreg.QueryValueEx(reg, cfg.api_key_env)[0]).strip()
            except OSError:
                key = ""
        return cls(cfg, key) if key and cfg.enabled else None

    def chat(self, msgs: list[dict], retries: int = 2) -> str:
        request = {
            "model": self.cfg.model,
            "messages": msgs,
            "response_format": {"type": "json_object"},
            "temperature": 0.7,
            "max_tokens": 2000,
            "stream": False,
        }
        if self.cfg.thinking in ("enabled", "disabled"):
            # DeepSeek: thinking is on (effort high) by default; retelling facts does not need it.
            request["thinking"] = {"type": self.cfg.thinking}
        body = json.dumps(request).encode("utf-8")
        last: Exception | None = None
        for attempt in range(retries + 1):
            req = urllib.request.Request(
                f"{self.cfg.base_url}/chat/completions",
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]
                content = (choice["message"].get("content") or "").strip()
                if choice.get("finish_reason") == "length":
                    last = LLMError("输出被截断（finish_reason=length）")
                elif content:
                    return content
                else:
                    last = LLMError("返回内容为空")
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:300]
                if e.code in (400, 401, 402, 403, 404, 422):
                    raise LLMError(f"HTTP {e.code}：{detail}") from None
                last = LLMError(f"HTTP {e.code}：{detail}")
            except (OSError, ValueError, KeyError, IndexError) as e:
                last = e
            time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"请求失败：{last}")


def _parse(text: str):
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except ValueError:
                pass
    return None


def shown_facts(kp: dict) -> list[dict]:
    return [f for f in kp["facts"] if f["type"] not in HIDDEN_FACTS]


def recheck(result: dict, kp: dict) -> list[str]:
    """Runs today's checks on a cached explanation (the rules grow as new inventions are found)."""
    return verify.verify({"sentences": result["sentences"], "tip": result["tip"]}, shown_facts(kp), kp["marks"])


def explain(client: Client, kp: dict, age: int, rank: str) -> dict:
    """Asks for an explanation, checks it, retries once with the violations. Never raises LLMError
    for bad content; the result says whether it was verified."""
    msgs = messages(kp, age, rank)
    shown = shown_facts(kp)
    attempts = []
    for _ in range(2):
        text = client.chat(msgs)
        output = _parse(text)
        problems = verify.verify(output, shown, kp["marks"])
        attempts.append({"output": output if output is not None else text, "problems": problems})
        if not problems:
            return {
                "sentences": output["sentences"],
                "tip": output["tip"],
                "model": client.cfg.model,
                "verified": True,
                "attempts": len(attempts),
            }
        msgs = msgs + [
            {"role": "assistant", "content": text},
            {
                "role": "user",
                "content": "这段讲解没有通过检查，问题如下：\n- " + "\n- ".join(problems)
                + "\n请按规则重写，只输出 json。",
            },
        ]
    return {"verified": False, "model": client.cfg.model, "attempts": len(attempts), "rejected": attempts}
