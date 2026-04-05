# -*- coding: utf-8 -*-
"""Agent 运行时状态跟踪。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Deque


@dataclass
class AgentStepTracker:
    """跟踪屏幕变化、动作历史与失败状态。"""

    last_screen_hash: str | None = None
    screen_unchanged_steps: int = 0
    consecutive_failures: int = 0
    stuck_warnings: int = 0
    recent_action_signatures: Deque[str] = field(
        default_factory=lambda: deque(maxlen=12)
    )
    recent_failures: Deque[str] = field(default_factory=lambda: deque(maxlen=5))

    @staticmethod
    def screen_hash(base64_data: str) -> str:
        """计算截图内容哈希。"""
        return sha1(base64_data.encode("utf-8")).hexdigest()

    @staticmethod
    def looks_like_loop(signatures: list[str]) -> bool:
        """判断最近动作是否呈现明显循环。"""
        if len(signatures) < 6:
            return False
        last6 = signatures[-6:]
        a, b = last6[0], last6[1]
        if a == b:
            return all(item == a for item in last6)
        return last6 == [a, b, a, b, a, b]

    def update_screen(self, base64_data: str) -> str:
        """根据当前截图更新屏幕稳定性状态。"""
        current_hash = self.screen_hash(base64_data)
        if self.last_screen_hash == current_hash:
            self.screen_unchanged_steps += 1
        else:
            self.screen_unchanged_steps = 0
        self.last_screen_hash = current_hash
        return current_hash

    def record_action(self, signature: str) -> None:
        """记录最近动作签名。"""
        self.recent_action_signatures.append(signature)

    def record_result(self, success: bool, message: str | None = None) -> None:
        """记录动作执行结果。"""
        if success:
            self.consecutive_failures = 0
            return
        self.consecutive_failures += 1
        if message:
            self.recent_failures.append(message)

    def is_action_loop(self) -> bool:
        """基于最近动作判断是否进入循环。"""
        return self.looks_like_loop(list(self.recent_action_signatures))

    def reset(self) -> None:
        """重置所有运行时状态。"""
        self.last_screen_hash = None
        self.screen_unchanged_steps = 0
        self.consecutive_failures = 0
        self.stuck_warnings = 0
        self.recent_action_signatures.clear()
        self.recent_failures.clear()
