# -*- coding: utf-8 -*-

import json
from types import SimpleNamespace

from phone_agent.agent_ios import IOSPhoneAgent


class TestIOSRuntimeInboxReset:
    def _make_agent(self, inbox_path: str):
        agent = IOSPhoneAgent.__new__(IOSPhoneAgent)
        agent.agent_config = SimpleNamespace(verbose=False)
        agent._runtime_inbox_path = inbox_path
        agent._consumed_instruction_ids = set()
        agent._inbox_file_position = 0
        agent._context = []
        agent._step_count = 0
        return agent

    @staticmethod
    def _read_user_texts(context: list[dict]) -> list[str]:
        texts: list[str] = []
        for message in context:
            content = message.get("content")
            if isinstance(content, str):
                texts.append(content)
                continue
            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))
        return texts

    def test_reset_clears_inbox_cursor_and_consumed_ids_for_new_task(self, tmp_path):
        inbox_path = tmp_path / "runtime_inbox.jsonl"
        inbox_path.write_text(
            json.dumps({"id": "ui-0001", "text": "第一条指令"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        agent = self._make_agent(str(inbox_path))

        agent._drain_runtime_user_instructions()

        first_texts = self._read_user_texts(agent._context)
        assert any("第一条指令" in text for text in first_texts)
        assert agent._consumed_instruction_ids == {"ui-0001"}
        assert agent._inbox_file_position > 0

        agent.reset()
        assert agent._context == []
        assert agent._step_count == 0
        assert agent._consumed_instruction_ids == set()
        assert agent._inbox_file_position == 0

        inbox_path.write_text(
            json.dumps({"id": "ui-0001", "text": "第二个任务的新指令"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        agent._drain_runtime_user_instructions()

        second_texts = self._read_user_texts(agent._context)
        assert any("第二个任务的新指令" in text for text in second_texts)
        assert agent._consumed_instruction_ids == {"ui-0001"}

    def test_drain_runtime_user_instructions_skips_duplicate_ids_without_reset(self, tmp_path):
        inbox_path = tmp_path / "runtime_inbox.jsonl"
        agent = self._make_agent(str(inbox_path))

        inbox_path.write_text(
            "".join(
                [
                    json.dumps({"id": "ui-0001", "text": "第一条"}, ensure_ascii=False) + "\n",
                    json.dumps({"id": "ui-0001", "text": "重复第一条"}, ensure_ascii=False) + "\n",
                ]
            ),
            encoding="utf-8",
        )

        agent._drain_runtime_user_instructions()

        texts = self._read_user_texts(agent._context)
        assert sum("第一条" in text or "重复第一条" in text for text in texts) == 1
        assert agent._consumed_instruction_ids == {"ui-0001"}
