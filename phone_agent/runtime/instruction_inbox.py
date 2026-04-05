# -*- coding: utf-8 -*-
"""运行时用户指令 inbox 读取器。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RuntimeInstructionInbox:
    """增量读取 JSONL inbox，并基于指令 ID 去重。"""

    path: str | None = None
    consumed_ids: set[str] = field(default_factory=set)
    file_position: int = 0

    def reset(self) -> None:
        """重置游标与去重状态。"""
        self.consumed_ids.clear()
        self.file_position = 0

    def exists(self) -> bool:
        """当前 inbox 文件是否存在。"""
        if not self.path:
            return False
        return Path(self.path).is_file()

    def read_new_entries(self) -> list[dict[str, str]]:
        """从当前游标开始读取新增且合法的指令条目。"""
        if not self.exists():
            return []

        inbox_path = Path(self.path)
        new_entries: list[dict[str, str]] = []
        with inbox_path.open("r", encoding="utf-8") as handle:
            handle.seek(self.file_position)
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(entry, dict):
                    continue
                if not entry.get("id") or not entry.get("text"):
                    continue
                new_entries.append(entry)
            self.file_position = handle.tell()
        return new_entries

    def consume_texts(self) -> list[str]:
        """读取新指令并返回去重后的文本内容。"""
        texts: list[str] = []
        for entry in self.read_new_entries():
            instruction_id = str(entry["id"])
            if instruction_id in self.consumed_ids:
                continue
            self.consumed_ids.add(instruction_id)
            text = str(entry["text"]).strip()
            if text:
                texts.append(text)
        return texts

    @staticmethod
    def wrap_user_instruction(text: str) -> str:
        """将 GUI 追加指令包装成适合注入模型上下文的 user message 文本。"""
        return (
            "[用户在任务执行中追加了新指令]\n"
            f"{text}\n"
            "请在后续步骤中优先遵循此指示（除非与原任务目标存在根本冲突）。"
        )

    @staticmethod
    def build_preview_texts(texts: list[str], max_items: int | None = None) -> list[str]:
        """构造日志预览文本。"""
        items = texts if max_items is None else texts[:max_items]
        return [text[:40] for text in items]
