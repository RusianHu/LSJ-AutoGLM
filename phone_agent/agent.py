"""Main PhoneAgent class for orchestrating phone automation."""

import json
import re
import traceback
from collections import deque
from dataclasses import dataclass
from hashlib import sha1
from typing import Any, Callable

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.actions.registry import (
    ActionPolicyInput,
    ResolvedActionPolicy,
    export_prompt_action_specs,
    resolve_action_policy,
)
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ExpertConfig, ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder
from phone_agent.prompts.prompt_sections import render_action_protocol_section


@dataclass
class AgentConfig:
    """Configuration for the PhoneAgent."""

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True
    use_thirdparty_prompt: bool = False
    thirdparty_thinking: bool = True
    platform: str | None = None
    action_policy: ActionPolicyInput | None = None
    runtime_action_policy: ResolvedActionPolicy | None = None
    expert_config: ExpertConfig | None = None
    runtime_inbox_path: str | None = None  # JSONL inbox for GUI-injected user instructions

    def __post_init__(self):
        normalized_lang = (self.lang or "cn").strip().lower()
        if normalized_lang == "zh":
            normalized_lang = "cn"
        self.lang = normalized_lang

        if self.platform is None:
            self.platform = get_device_factory().device_type.value

        if self.runtime_action_policy is None:
            self.runtime_action_policy = resolve_action_policy(
                self.platform,
                self.action_policy,
            )

        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(
                self.lang,
                platform=self.platform,
                thirdparty=self.use_thirdparty_prompt,
                thirdparty_thinking=self.thirdparty_thinking,
                action_policy=self.action_policy,
            )


@dataclass
class StepResult:
    """Result of a single agent step."""

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None


class PhoneAgent:
    """
    AI-powered agent for automating Android phone interactions.

    The agent uses a vision-language model to understand screen content
    and decide on actions to complete user tasks.

    Args:
        model_config: Configuration for the AI model.
        agent_config: Configuration for the agent behavior.
        confirmation_callback: Optional callback for sensitive action confirmation.
        takeover_callback: Optional callback for takeover requests.

    Example:
        >>> from phone_agent import PhoneAgent
        >>> from phone_agent.model import ModelConfig
        >>>
        >>> model_config = ModelConfig(base_url="http://localhost:8000/v1")
        >>> agent = PhoneAgent(model_config)
        >>> agent.run("Open WeChat and send a message to John")
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config or ModelConfig()
        self.agent_config = agent_config or AgentConfig()

        self.model_client = ModelClient(self.model_config)
        self.expert_client = (
            ModelClient(
                ModelConfig(
                    base_url=self.agent_config.expert_config.base_url,
                    model_name=self.agent_config.expert_config.model_name,
                    api_key=self.agent_config.expert_config.api_key or "EMPTY",
                    max_tokens=self.agent_config.expert_config.max_tokens,
                    temperature=self.agent_config.expert_config.temperature,
                    top_p=self.agent_config.expert_config.top_p,
                    frequency_penalty=self.agent_config.expert_config.frequency_penalty,
                    extra_body=self.agent_config.expert_config.extra_body,
                    lang=self.agent_config.expert_config.lang,
                )
            )
            if self.agent_config.expert_config and self.agent_config.expert_config.enabled
            else None
        )
        self.action_handler = ActionHandler(
            device_id=self.agent_config.device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            expert_assist_callback=self._handle_expert_action,
            runtime_policy=self.agent_config.runtime_action_policy,
        )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._last_screen_hash: str | None = None
        self._screen_unchanged_steps = 0
        self._recent_action_signatures: deque[str] = deque(maxlen=12)
        self._recent_failures: deque[str] = deque(maxlen=5)
        self._stuck_warnings = 0
        self._task_text = ""
        self._consecutive_failures = 0
        self._expert_guidance_count = 0
        self._expert_rescue_count = 0
        self._last_expert_trigger_step = 0

        # 运行时用户指令收件箱（GUI 桥接）
        self._runtime_inbox_path: str | None = (
            getattr(self.agent_config, "runtime_inbox_path", None) or None
        )
        self._consumed_instruction_ids: set[str] = set()   # 已消费指令 ID 去重集合
        self._inbox_file_position: int = 0                  # 文件读取游标（字节偏移）

    @staticmethod
    def _screen_hash(base64_data: str) -> str:
        return sha1(base64_data.encode("utf-8")).hexdigest()

    @staticmethod
    def _action_signature(action: dict[str, Any]) -> str:
        if action.get("_metadata") == "finish":
            return "finish"
        name = action.get("action")
        if name == "Tap":
            return f"Tap:{action.get('element')}"
        if name == "Swipe":
            return f"Swipe:{action.get('start')}->{action.get('end')}"
        if name == "Type":
            return f"Type:{action.get('text')}"
        if name == "Launch":
            return f"Launch:{action.get('app')}"
        if name == "Wait":
            return f"Wait:{action.get('duration')}"
        if name == "Take_over":
            return "Take_over"
        return str(name)

    @staticmethod
    def _looks_like_loop(signatures: list[str]) -> bool:
        if len(signatures) < 6:
            return False
        last6 = signatures[-6:]
        a, b = last6[0], last6[1]
        if a == b:
            return all(x == a for x in last6)
        return last6 == [a, b, a, b, a, b]

    @staticmethod
    def _message_text(message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                item.get("text", "") for item in content if item.get("type") == "text"
            )
        return ""

    def _find_recommended_followup_action(self) -> dict[str, Any] | None:
        for message in reversed(self._context):
            if message.get("role") != "user":
                continue
            text = self._message_text(message)
            if "** Action Result **" not in text:
                continue

            match = re.search(r'do\(action="(?:Find_App|Launch)".*?\)', text)
            if not match:
                return None

            try:
                return parse_action(match.group(0))
            except ValueError:
                return None
        return None

    @staticmethod
    def _should_follow_recommended_action(
        action: dict[str, Any], recommended_action: dict[str, Any] | None
    ) -> bool:
        if not recommended_action:
            return False
        if recommended_action.get("_metadata") != "do":
            return False
        if recommended_action.get("action") not in ("Find_App", "Launch"):
            return False

        if action.get("_metadata") != "do":
            return True

        if action.get("action") != recommended_action.get("action"):
            return True

        if action.get("action") == "Find_App":
            return (action.get("query") or "") != (recommended_action.get("query") or "")

        if action.get("action") == "Launch":
            return (action.get("app") or "") != (recommended_action.get("app") or "")

        return False

    @staticmethod
    def _looks_like_terminal_note_message(message: str | None) -> bool:
        normalized = (message or "").strip().lower()
        if not normalized:
            return False

        terminal_markers = (
            "任务完成",
            "已完成",
            "已经完成",
            "完成任务",
            "已查看",
            "可以看到",
            "当前页面已经是",
            "当前屏幕显示的是",
            "最新记录",
            "最新历史记录",
            "最终结果",
            "结果为",
            "结果是",
            "task completed",
            "already complete",
            "already completed",
            "final result",
            "result is",
            "latest record",
            "latest history",
        )
        return any(marker in normalized for marker in terminal_markers)

    @staticmethod
    def _normalize_thirdparty_terminal_note(
        action: dict[str, Any], *, use_thirdparty_prompt: bool
    ) -> dict[str, Any]:
        if not use_thirdparty_prompt:
            return action
        if action.get("_metadata") != "do" or action.get("action") != "Note":
            return action

        message = (action.get("message") or "").strip()
        if not PhoneAgent._looks_like_terminal_note_message(message):
            return action

        return finish(message=message)

    def run(self, task: str) -> str:
        """
        Run the agent to complete a task.

        Args:
            task: Natural language description of the task.

        Returns:
            Final message from the agent.
        """
        self._context = []
        self._step_count = 0
        self._task_text = task

        # First step with user prompt
        result = self._execute_step(task, is_first=True)

        if result.finished:
            return result.message or "Task completed"

        # Continue until finished or max steps reached
        while self._step_count < self.agent_config.max_steps:
            result = self._execute_step(is_first=False)

            if result.finished:
                return result.message or "Task completed"

        return "Max steps reached"

    def step(self, task: str | None = None) -> StepResult:
        """
        Execute a single step of the agent.

        Useful for manual control or debugging.

        Args:
            task: Task description (only needed for first step).

        Returns:
            StepResult with step details.
        """
        is_first = len(self._context) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._context = []
        self._step_count = 0
        self._last_screen_hash = None
        self._screen_unchanged_steps = 0
        self._recent_action_signatures.clear()
        self._recent_failures.clear()
        self._stuck_warnings = 0
        self._task_text = ""
        self._consecutive_failures = 0
        self._expert_guidance_count = 0
        self._expert_rescue_count = 0
        self._last_expert_trigger_step = 0

    def _build_expert_prompt(self) -> str:
        expert_config = self.agent_config.expert_config
        if expert_config and expert_config.prompt.strip():
            return expert_config.prompt.strip()
        action_policy = self.agent_config.runtime_action_policy
        platform = self.agent_config.platform or "adb"
        action_specs = export_prompt_action_specs(
            platform,
            lang=self.agent_config.lang,
            include_actions=action_policy.ai_visible_actions if action_policy else (),
            thirdparty=False,
            minimal=False,
        )
        action_protocol = render_action_protocol_section(
            action_specs,
            lang=self.agent_config.lang,
            include_examples=True,
            include_rules=True,
        )
        runtime_enabled = ", ".join(action_policy.runtime_enabled_actions) if action_policy else ""
        ai_visible = ", ".join(action_policy.ai_visible_actions) if action_policy else ""
        return (
            "你是一个手机自动化任务专家顾问。你的职责是基于任务目标、当前截图、页面状态、"
            "最近动作与失败信息，给出简明、可执行、贴合当前工具约束的指导建议。"
            "\n要求："
            "\n1. 不要输出 do()/finish()；"
            "\n2. 不要假设不存在的工具；"
            "\n3. 只围绕当前 AI 可见动作和运行时允许运行动作给建议；"
            "\n4. 优先指出当前卡点原因、下一步策略、以及若失败时的替代思路。"
            f"\n\nAI 可见动作：{ai_visible or '（无）'}"
            f"\n运行时允许运行动作：{runtime_enabled or '（无）'}"
            f"\n\n动作协议参考：\n{action_protocol}"
        )

    @staticmethod
    def _truncate_log_text(text: str, max_chars: int = 1200, max_lines: int = 12) -> str:
        normalized = (text or "").strip().replace("\r\n", "\n")
        if not normalized:
            return ""
        lines = [line.rstrip() for line in normalized.split("\n")]
        if len(lines) > max_lines:
            lines = lines[:max_lines] + ["...(已截断)"]
        truncated = "\n".join(lines)
        if len(truncated) > max_chars:
            truncated = truncated[: max_chars - 9].rstrip() + "...(已截断)"
        return truncated

    @staticmethod
    def _expert_reason_label(reason: str) -> str:
        mapping = {
            "init": "初始化",
            "strict_step": "严格模式逐步咨询",
            "manual_action": "Ask_AI 手动求助",
            "screen_unchanged": "页面长时间无变化",
            "consecutive_failures": "连续动作失败",
            "action_loop": "动作循环",
        }
        return mapping.get(reason, reason)

    @staticmethod
    def _print_expert_log(message: str) -> None:
        print(f"[EXPERT] {message}", flush=True)

    def _log_expert_guidance(self, reason: str, guidance: str) -> None:
        preview = self._truncate_log_text(guidance)
        if not preview:
            return
        reason_label = self._expert_reason_label(reason)
        self._print_expert_log(f"专家建议（{reason_label}）")
        for line in preview.split("\n"):
            if line.strip():
                self._print_expert_log(f"  {line}")
            else:
                self._print_expert_log("")

    def _request_expert_guidance(
        self,
        *,
        reason: str,
        screenshot_base64: str,
        current_app: str,
        extra_message: str = "",
    ) -> str | None:
        expert_config = self.agent_config.expert_config
        if not expert_config or not expert_config.enabled or self.expert_client is None:
            return None
        action_policy = self.agent_config.runtime_action_policy
        screen_info = MessageBuilder.build_screen_info(
            current_app,
            step=self._step_count,
            screen_unchanged_steps=self._screen_unchanged_steps,
            recent_actions=list(self._recent_action_signatures),
            recent_failures=list(self._recent_failures),
            trigger_reason=reason,
            ai_visible_actions=list(action_policy.ai_visible_actions) if action_policy else [],
            runtime_enabled_actions=list(action_policy.runtime_enabled_actions) if action_policy else [],
            last_expert_trigger_step=self._last_expert_trigger_step,
            expert_guidance_count=self._expert_guidance_count,
        )
        task_text = self._task_text or extra_message or ""
        prompt = self._build_expert_prompt()
        recent_context = []
        for message in self._context[-6:]:
            text = self._message_text(message).strip()
            if text:
                recent_context.append(f"[{message.get('role', 'unknown')}] {text}")
        recent_context_text = "\n\n".join(recent_context).strip()
        user_text = (
            f"任务：{task_text}\n\n"
            f"触发原因：{reason}\n\n"
            f"当前运行状态：\n{screen_info}"
        )
        if recent_context_text:
            user_text += f"\n\n最近上下文摘录：\n{recent_context_text}"
        if extra_message:
            user_text += f"\n\n补充问题：{extra_message}"
        messages = [
            MessageBuilder.create_system_message(prompt),
            MessageBuilder.create_user_message(text=user_text, image_base64=screenshot_base64),
        ]
        reason_label = self._expert_reason_label(reason)
        self._print_expert_log(
            f"发起专家请求：{reason_label}｜步骤 {self._step_count}｜当前应用 {current_app}"
        )
        try:
            response = self.expert_client.request_text(messages)
        except Exception as exc:
            self._print_expert_log(f"专家请求失败：{reason_label}｜错误 {exc}")
            if self.agent_config.verbose:
                traceback.print_exc()
            return None
        guidance = (response.guidance or "").strip()
        if not guidance:
            self._print_expert_log(f"专家请求失败：{reason_label}｜返回空建议")
            return None
        self._print_expert_log(
            f"专家请求成功：{reason_label}｜耗时 {response.total_time:.2f}s｜{len(guidance)} 字符"
        )
        self._log_expert_guidance(reason, guidance)
        return guidance

    def _inject_expert_guidance(self, guidance: str, reason: str) -> None:
        text = (
            f"** Expert Guidance **\n\n"
            f"Trigger: {reason}\n\n{guidance}"
        )
        self._context.append(MessageBuilder.create_user_message(text=text))

    def _should_trigger_expert_rescue(self) -> str | None:
        expert_config = self.agent_config.expert_config
        if not expert_config or not expert_config.enabled or not expert_config.auto_rescue:
            return None
        if self._expert_rescue_count >= expert_config.max_rescues:
            return None
        if self._step_count - self._last_expert_trigger_step <= 1:
            return None
        if self._screen_unchanged_steps >= expert_config.screen_unchanged_threshold:
            return "screen_unchanged"
        if self._consecutive_failures >= expert_config.consecutive_failure_threshold:
            return "consecutive_failures"
        if self._looks_like_loop(list(self._recent_action_signatures)):
            return "action_loop"
        return None

    def _strict_expert_guidance_decision(self) -> tuple[bool, str]:
        expert_config = self.agent_config.expert_config
        if not expert_config or not expert_config.enabled:
            return False, "专家模式未启用"
        if not expert_config.strict_mode:
            return False, "严格模式未启用"
        if self.expert_client is None:
            return False, "专家客户端不可用"
        if self._last_expert_trigger_step == self._step_count:
            return False, "本步已存在专家建议，跳过重复咨询"
        return True, "允许触发严格模式专家咨询"

    # ---------- 运行时用户指令收件箱（GUI 桥接） ----------

    def _drain_runtime_user_instructions(self):
        """
        从 JSONL inbox 文件读取并消费 GUI 追加的用户指令。

        每次调用时从上次读取位置（游标）开始，将新指令以 user message
        形式追加到 self._context 中。消费后打印日志供 GUI 日志区可见。

        设计要点：
        - 使用文件偏移量游标（非全量重读），避免大文件性能问题
        - 基于 instruction id 去重，防止重复注入
        - IO 异常时静默跳过，不影响主任务循环
        """
        if not self._runtime_inbox_path:
            return
        import os as _os

        inbox_path = self._runtime_inbox_path
        if not _os.path.isfile(inbox_path):
            return

        new_instructions: list[dict] = []
        try:
            with open(inbox_path, "r", encoding="utf-8") as f:
                # 从上次游标位置开始 seek
                f.seek(self._inbox_file_position)
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if isinstance(entry, dict) and entry.get("id") and entry.get("text"):
                            new_instructions.append(entry)
                    except (json.JSONDecodeError, TypeError):
                        # 跳过损坏行，不中断流程
                        pass
                # 更新游标到文件末尾
                self._inbox_file_position = f.tell()
        except Exception as exc:
            if self.agent_config.verbose:
                print(f"[WARN] 读取运行时指令 inbox 失败: {exc}")
            return

        if not new_instructions:
            return

        injected_count = 0
        for entry in new_instructions:
            instr_id = entry["id"]
            if instr_id in self._consumed_instruction_ids:
                continue
            self._consumed_instruction_ids.add(instr_id)

            text = entry["text"]
            # 将用户追加指令包装为一条 user message 注入上下文
            wrapper_text = (
                "[用户在任务执行中追加了新指令]\n"
                f"{text}\n"
                "请在后续步骤中优先遵循此指示（除非与原任务目标存在根本冲突）。"
            )
            self._context.append(
                MessageBuilder.create_user_message(text=wrapper_text)
            )
            injected_count += 1

        if injected_count > 0:
            preview_texts = [e["text"][:40] for e in new_instructions[:injected_count]]
            print(
                f"\n{'=' * 50}\n"
                f"[RUNTIME INSTRUCTION] 已接收 {injected_count} 条运行中用户指令并注入主模型上下文\n"
                f"  预览: {'; '.join(preview_texts)}\n"
                f"{'=' * 50}\n",
                flush=True,
            )

    def _handle_expert_action(self, action: dict[str, Any]) -> str | None:
        expert_config = self.agent_config.expert_config
        if not expert_config or not expert_config.enabled or not expert_config.manual_action:
            self._print_expert_log("Ask_AI 请求被拒绝：专家模式未启用或未允许手动求助")
            return "专家模式未启用或未允许 Ask_AI 动作"
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(self.agent_config.device_id)
        current_app = device_factory.get_current_app(self.agent_config.device_id)
        extra_message = (action.get("message") or "").strip()
        self._print_expert_log(
            f"Ask_AI 请求专家协助：{self._truncate_log_text(extra_message, max_chars=200, max_lines=3) or '（未提供补充问题）'}"
        )
        guidance = self._request_expert_guidance(
            reason="manual_action",
            screenshot_base64=screenshot.base64_data,
            current_app=current_app,
            extra_message=extra_message,
        )
        if not guidance:
            return "专家模型未返回有效建议"
        self._inject_expert_guidance(guidance, "manual_action")
        self._expert_guidance_count += 1
        self._last_expert_trigger_step = self._step_count
        self._print_expert_log("专家建议已注入主模型上下文（Ask_AI）")
        return "专家建议已注入上下文"

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Capture current screen state
        device_factory = get_device_factory()
        screenshot = device_factory.get_screenshot(self.agent_config.device_id)
        current_app = device_factory.get_current_app(self.agent_config.device_id)
        current_hash = self._screen_hash(screenshot.base64_data)
        if self._last_screen_hash == current_hash:
            self._screen_unchanged_steps += 1
        else:
            self._screen_unchanged_steps = 0
        self._last_screen_hash = current_hash

        # --- 消费运行时用户指令（GUI 追加指令 inbox） ---
        self._drain_runtime_user_instructions()

        # Build messages
        rescue_reason = None if is_first else self._should_trigger_expert_rescue()
        if is_first:
            screen_info = MessageBuilder.build_screen_info(current_app)
            self._context.append(
                MessageBuilder.create_system_message(self.agent_config.system_prompt)
            )
            text_content = f"{user_prompt}\n\n{screen_info}"
            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )
            expert_config = self.agent_config.expert_config
            if expert_config and expert_config.enabled and expert_config.auto_init:
                guidance = self._request_expert_guidance(
                    reason="init",
                    screenshot_base64=screenshot.base64_data,
                    current_app=current_app,
                )
                if guidance:
                    self._inject_expert_guidance(guidance, "init")
                    self._expert_guidance_count += 1
                    self._last_expert_trigger_step = self._step_count
                    self._print_expert_log("专家建议已注入主模型上下文（初始化）")
        else:
            if rescue_reason:
                self._print_expert_log(
                    f"触发自动专家救援：{self._expert_reason_label(rescue_reason)}"
                )
                guidance = self._request_expert_guidance(
                    reason=rescue_reason,
                    screenshot_base64=screenshot.base64_data,
                    current_app=current_app,
                )
                if guidance:
                    self._inject_expert_guidance(guidance, rescue_reason)
                    self._expert_guidance_count += 1
                    self._expert_rescue_count += 1
                    self._last_expert_trigger_step = self._step_count
                    self._print_expert_log(
                        f"专家建议已注入主模型上下文（{self._expert_reason_label(rescue_reason)}）"
                    )
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"** Screen Info **\n\n{screen_info}"
            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )

        strict_should_trigger, strict_reason = self._strict_expert_guidance_decision()
        if strict_should_trigger:
            self._print_expert_log(
                f"触发严格模式专家咨询：第 {self._step_count} 步"
            )
            strict_guidance = self._request_expert_guidance(
                reason="strict_step",
                screenshot_base64=screenshot.base64_data,
                current_app=current_app,
            )
            if strict_guidance:
                self._inject_expert_guidance(strict_guidance, "strict_step")
                self._expert_guidance_count += 1
                self._last_expert_trigger_step = self._step_count
                self._print_expert_log("专家建议已注入主模型上下文（严格模式）")
        elif self.agent_config.expert_config and self.agent_config.expert_config.strict_mode:
            self._print_expert_log(f"跳过严格模式专家咨询：{strict_reason}")

        # Get model response
        try:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "=" * 50)
            print(f"💭 {msgs['thinking']}:")
            print("-" * 50)
            response = self.model_client.request(self._context)
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Model error: {e}",
            )

        # Remove image from context to save space (even if parsing fails / retries)
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

        # Add assistant response to context
        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
            )
        )

        # Parse action from response
        try:
            action = parse_action(response.action)
        except ValueError as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking=response.thinking,
                message=f"Failed to parse action: {e}",
            )

        if action is None:
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking=response.thinking,
                message="动作解析失败，无法继续执行",
            )

        recommended_action = self._find_recommended_followup_action()
        if self._should_follow_recommended_action(action, recommended_action):
            if self.agent_config.verbose and recommended_action is not None:
                print(
                    "🔒 Overriding model action with recommended follow-up:",
                    json.dumps(recommended_action, ensure_ascii=False),
                )
            action = recommended_action or action

        normalized_action = self._normalize_thirdparty_terminal_note(
            action,
            use_thirdparty_prompt=self.agent_config.use_thirdparty_prompt,
        )
        if self.agent_config.verbose and normalized_action is not action:
            print(
                "🧩 Normalizing thirdparty completion note to finish:",
                json.dumps(normalized_action, ensure_ascii=False),
            )
        action = normalized_action

        # Track recent actions for loop detection & better thirdparty guidance.
        self._recent_action_signatures.append(self._action_signature(action))

        if self.agent_config.verbose:
            # Print thinking process
            print("-" * 50)
            print(f"🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        # Execute action
        try:
            result = self.action_handler.execute(
                action, screenshot.width, screenshot.height
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = self.action_handler.execute(
                finish(message=str(e)), screenshot.width, screenshot.height
            )

        if result.message:
            result_prefix = "Action succeeded" if result.success else "Action failed"
            self._context.append(
                MessageBuilder.create_user_message(
                    text=f"** Action Result **\n\n{result_prefix}: {result.message}"
                )
            )

        if result.success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            if result.message:
                self._recent_failures.append(result.message)

        if self.agent_config.verbose and (not result.success) and result.message:
            print(f"⚠️ Action failed: {result.message}")

        # Check if finished
        finished = action.get("_metadata") == "finish" or result.should_finish

        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "🎉 " + "=" * 48)
            print(
                f"✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}"
            )
            print("=" * 50 + "\n")

        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=result.message or action.get("message"),
        )

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get the current conversation context."""
        return self._context.copy()

    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count
