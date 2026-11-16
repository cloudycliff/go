"""Runs `katago analysis` and talks to it in its JSON-lines protocol."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from queue import Empty, Queue

from .config import ROOT, KataGoPaths


class KataGoError(RuntimeError):
    pass


class KataGo:
    def __init__(self, paths: KataGoPaths, use_human_model: bool = True) -> None:
        for label, path in (("KataGo", paths.exe), ("权重", paths.model), ("配置", paths.config)):
            if not path.exists():
                raise KataGoError(f"找不到{label}文件：{path}")
        cmd = [
            str(paths.exe),
            "analysis",
            "-model",
            str(paths.model),
            "-config",
            str(paths.config),
        ]
        if use_human_model:
            if not paths.human_model.exists():
                raise KataGoError(f"找不到 HumanSL 模型：{paths.human_model}")
            cmd += ["-human-model", str(paths.human_model)]
        (ROOT / "logs" / "katago").mkdir(parents=True, exist_ok=True)
        self._stderr_tail: list[str] = []
        self._proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._responses: Queue[dict] = Queue()
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self._proc.stdout
        for line in self._proc.stdout:
            line = line.strip()
            if line:
                try:
                    self._responses.put(json.loads(line))
                except ValueError:
                    self._stderr_tail.append(line)
        self._responses.put({"_eof": True})

    def _read_stderr(self) -> None:
        assert self._proc.stderr
        for line in self._proc.stderr:
            self._stderr_tail = (self._stderr_tail + [line.rstrip()])[-40:]

    def send(self, query: dict) -> None:
        if self._proc.poll() is not None:
            raise KataGoError("KataGo 已退出：\n" + "\n".join(self._stderr_tail))
        assert self._proc.stdin
        self._proc.stdin.write(json.dumps(query) + "\n")
        self._proc.stdin.flush()

    def responses(self, query_id: str, count: int, timeout: float = 600.0, on_each=None):
        """Collects `count` responses for one query (one per analyzed turn)."""
        got: dict[int, dict] = {}
        while len(got) < count:
            try:
                resp = self._responses.get(timeout=timeout)
            except Empty:
                raise KataGoError(f"KataGo 超过 {timeout:.0f} 秒没有返回结果")
            if resp.get("_eof"):
                raise KataGoError("KataGo 意外退出：\n" + "\n".join(self._stderr_tail))
            if "error" in resp:
                raise KataGoError(f"KataGo 报错：{resp['error']}（字段 {resp.get('field')}）")
            if "warning" in resp:
                self._stderr_tail.append(f"warning: {resp}")
                continue
            if resp.get("id") != query_id or resp.get("isDuringSearch"):
                continue
            got[resp["turnNumber"]] = resp
            if on_each:
                on_each(len(got), count)
        return [got[t] for t in sorted(got)]

    def version(self, timeout: float = 120.0) -> dict:
        """KataGo version and git hash; also waits until the engine has loaded its models."""
        self.send({"id": "version", "action": "query_version"})
        while True:
            try:
                resp = self._responses.get(timeout=timeout)
            except Empty:
                raise KataGoError("KataGo 启动超时")
            if resp.get("_eof"):
                raise KataGoError("KataGo 启动失败：\n" + "\n".join(self._stderr_tail))
            if resp.get("id") == "version":
                return {"version": resp.get("version"), "git": resp.get("git_hash")}

    def warnings(self) -> list[str]:
        return [line for line in self._stderr_tail if line.startswith("warning:")]

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                assert self._proc.stdin
                self._proc.stdin.close()
                self._proc.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                self._proc.kill()

    def __enter__(self) -> "KataGo":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
