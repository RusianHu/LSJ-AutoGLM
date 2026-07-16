from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication

import main
from gui.services.config_service import ConfigService
from phone_agent.agent import AgentConfig, PhoneAgent
from phone_agent.config import get_system_prompt
from phone_agent.model.client import ModelClient


ROOT = Path(__file__).resolve().parents[1]


def test_only_standard_prompt_api_is_exposed():
    signature = inspect.signature(get_system_prompt)
    assert "thirdparty" not in signature.parameters
    assert "thirdparty_thinking" not in signature.parameters
    assert not (ROOT / "phone_agent" / "config" / "prompts_thirdparty.py").exists()

    prompt = get_system_prompt("cn", platform="adb")
    assert '<think>{think}</think>' in prompt
    assert 'finish(message="完成说明")' in prompt
    assert 'do(action="Find_App", query="keyword")' in prompt

    config = AgentConfig(verbose=False, platform="adb")
    assert config.system_prompt == prompt


def test_response_parser_accepts_structured_reasoned_and_action_only_outputs():
    parse = lambda content: ModelClient._parse_response(None, content)  # type: ignore[arg-type]

    thinking, action = parse(
        '<think>点击设置入口</think><answer>do(action="Tap", element=[500, 500])</answer>'
    )
    assert thinking == "点击设置入口"
    assert action == 'do(action="Tap", element=[500, 500])'

    thinking, action = parse('当前页面已加载，下一步点击。\ndo(action="Tap", element=[400, 600])')
    assert thinking == "当前页面已加载，下一步点击。"
    assert action == 'do(action="Tap", element=[400, 600])'

    assert parse('do(action="Back")') == ("", 'do(action="Back")')


def test_terminal_note_normalization_is_generic_but_avoids_prefix_false_positive():
    terminal = {"_metadata": "do", "action": "Note", "message": "任务完成：已找到目标记录"}
    normalized = PhoneAgent._normalize_terminal_note(terminal)
    assert normalized == {"_metadata": "finish", "message": "任务完成：已找到目标记录"}

    intermediate = {"_metadata": "do", "action": "Note", "message": "任务完成前还需要确认订单"}
    assert PhoneAgent._normalize_terminal_note(intermediate) is intermediate


def test_legacy_prompt_flags_are_accepted_but_hidden(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--thirdparty", "--thirdparty-no-thinking", "打开设置"],
    )
    args = main.parse_args()
    assert args.legacy_prompt_mode is True
    assert args.legacy_prompt_thinking is False

    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--thirdparty" not in result.stdout
    assert "--compress-image" in result.stdout
    assert "--no-compress-image" in result.stdout


def test_screenshot_compression_resolution_is_channel_independent(monkeypatch):
    monkeypatch.delenv("PHONE_AGENT_COMPRESS_IMAGE", raising=False)
    monkeypatch.delenv("PHONE_AGENT_NO_COMPRESS_IMAGE", raising=False)
    assert main._configure_screenshot_compression(None) is False

    monkeypatch.setenv("PHONE_AGENT_COMPRESS_IMAGE", "true")
    assert main._configure_screenshot_compression(None) is True

    monkeypatch.setenv("PHONE_AGENT_NO_COMPRESS_IMAGE", "true")
    assert main._configure_screenshot_compression(None) is False
    assert "PHONE_AGENT_COMPRESS_IMAGE" not in os.environ

    assert main._configure_screenshot_compression(True) is True
    assert os.environ["PHONE_AGENT_COMPRESS_IMAGE"] == "true"
    assert main._configure_screenshot_compression(False) is False
    assert "PHONE_AGENT_COMPRESS_IMAGE" not in os.environ


def test_gui_command_uses_unified_prompt_and_explicit_compression_flag(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    assert app is not None
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT=true\n"
        "OPEN_AUTOGLM_THIRDPARTY_THINKING=false\n",
        encoding="utf-8",
    )
    config = ConfigService(env_file=env_file)

    args = config.build_command_args("打开设置")
    assert "--thirdparty" not in args
    assert "--thirdparty-thinking" not in args
    assert "--thirdparty-no-thinking" not in args
    assert "--no-compress-image" in args

    config.set("OPEN_AUTOGLM_COMPRESS_IMAGE", "true")
    args = config.build_command_args("打开设置")
    assert "--compress-image" in args
    assert "--no-compress-image" not in args
    config.shutdown()
