from __future__ import annotations

from phone_agent.actions.handler import parse_action


def test_parse_action_preserves_markdown_fence_inside_type_text():
    text = (
        "# 这是一个标题\n\n"
        "**这是粗体文本**\n\n"
        "*这是斜体文本*\n\n"
        "```python\n"
        "print('Hello, World!')\n"
        "```\n\n"
        "- 列表项1\n"
        "- 列表项2"
    )
    response = f'do(action="Type", text="{text}")'

    assert parse_action(response) == {
        "_metadata": "do",
        "action": "Type",
        "text": text,
    }


def test_parse_action_still_unwraps_an_outer_markdown_fence():
    response = '```python\ndo(action="Tap", element=[120, 240])\n```'

    assert parse_action(response) == {
        "_metadata": "do",
        "action": "Tap",
        "element": [120, 240],
    }
