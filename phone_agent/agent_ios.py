"""iOS PhoneAgent class for orchestrating iOS phone automation."""

import json
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.actions.handler_ios import IOSActionHandler
from phone_agent.actions.registry import (
    ActionPolicyInput,
    ResolvedActionPolicy,
    resolve_action_policy,
)
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder
from phone_agent.xctest import XCTestConnection, get_current_app, get_screenshot


@dataclass
class IOSAgentConfig:
    """Configuration for the iOS PhoneAgent."""

    max_steps: int = 100
    wda_url: str = "http://localhost:8100"
    session_id: str | None = None
    device_id: str | None = None  # iOS device UDID
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True
    platform: str = "ios"
    action_policy: ActionPolicyInput | None = None
    runtime_action_policy: ResolvedActionPolicy | None = None
    runtime_inbox_path: str | None = None  # JSONL inbox for GUI-injected user instructions

    def __post_init__(self):
        normalized_lang = (self.lang or "cn").strip().lower()
        if normalized_lang == "zh":
            normalized_lang = "cn"
        self.lang = normalized_lang

        if self.runtime_action_policy is None:
            self.runtime_action_policy = resolve_action_policy(
                self.platform,
                self.action_policy,
            )

        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(
                self.lang,
                platform=self.platform,
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


class IOSPhoneAgent:
    """
    AI-powered agent for automating iOS phone interactions.

    The agent uses a vision-language model to understand screen content
    and decide on actions to complete user tasks via WebDriverAgent.

    Args:
        model_config: Configuration for the AI model.
        agent_config: Configuration for the iOS agent behavior.
        confirmation_callback: Optional callback for sensitive action confirmation.
        takeover_callback: Optional callback for takeover requests.

    Example:
        >>> from phone_agent.agent_ios import IOSPhoneAgent, IOSAgentConfig
        >>> from phone_agent.model import ModelConfig
        >>>
        >>> model_config = ModelConfig(base_url="http://localhost:8000/v1")
        >>> agent_config = IOSAgentConfig(wda_url="http://localhost:8100")
        >>> agent = IOSPhoneAgent(model_config, agent_config)
        >>> agent.run("Open Safari and search for Apple")
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: IOSAgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config or ModelConfig()
        self.agent_config = agent_config or IOSAgentConfig()

        self.model_client = ModelClient(self.model_config)

        # Initialize WDA connection and create session if needed
        self.wda_connection = XCTestConnection(wda_url=self.agent_config.wda_url)

        # Auto-create session if not provided
        if self.agent_config.session_id is None:
            success, session_id = self.wda_connection.start_wda_session()
            if success and session_id != "session_started":
                self.agent_config.session_id = session_id
                if self.agent_config.verbose:
                    print(f"✅ Created WDA session: {session_id}")
            elif self.agent_config.verbose:
                print(f"⚠️  Using default WDA session (no explicit session ID)")

        self.action_handler = IOSActionHandler(
            wda_url=self.agent_config.wda_url,
            session_id=self.agent_config.session_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
            runtime_policy=self.agent_config.runtime_action_policy,
        )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0

        # 运行时用户指令收件箱（GUI 桥接）
        self._runtime_inbox_path: str | None = (
            getattr(self.agent_config, "runtime_inbox_path", None) or None
        )
        self._consumed_instruction_ids: set[str] = set()
        self._inbox_file_position: int = 0

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

    # ---------- 运行时用户指令收件箱（GUI 桥接） ----------

    def _drain_runtime_user_instructions(self):
        """
        从 JSONL inbox 文件读取并消费 GUI 追加的用户指令。

        与 phone_agent/agent.py 中的同名方法逻辑一致：
        使用文件偏移量游标 + instruction id 去重，将新指令以 user message
        形式追加到 self._context 中。
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
                        pass
                self._inbox_file_position = f.tell()
        except Exception as exc:
            if self.agent_config.verbose:
                print(f"[WARN] 读取运行时指令 inbox 失败 (iOS): {exc}")
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
                f"[RUNTIME INSTRUCTION iOS] 已接收 {injected_count} 条运行中用户指令并注入主模型上下文\n"
                f"  预览: {'; '.join(preview_texts)}\n"
                f"{'=' * 50}\n",
                flush=True,
            )

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Capture current screen state
        screenshot = get_screenshot(
            wda_url=self.agent_config.wda_url,
            session_id=self.agent_config.session_id,
            device_id=self.agent_config.device_id,
        )
        current_app = get_current_app(
            wda_url=self.agent_config.wda_url, session_id=self.agent_config.session_id
        )

        # --- 消费运行时用户指令（GUI 追加指令 inbox） ---
        self._drain_runtime_user_instructions()

        # Build messages
        if is_first:
            self._context.append(
                MessageBuilder.create_system_message(self.agent_config.system_prompt)
            )

            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"{user_prompt}\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )
        else:
            screen_info = MessageBuilder.build_screen_info(current_app)
            text_content = f"** Screen Info **\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )

        # Get model response
        try:
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

        # Parse action from response
        try:
            action = parse_action(response.action)
        except ValueError:
            if self.agent_config.verbose:
                traceback.print_exc()
            action = finish(message=response.action)

        if self.agent_config.verbose:
            # Print thinking process
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "=" * 50)
            print(f"💭 {msgs['thinking']}:")
            print("-" * 50)
            print(response.thinking)
            print("-" * 50)
            print(f"🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        # Remove image from context to save space
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

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

        # Add assistant response to context
        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
            )
        )

        if result.message:
            result_prefix = "Action succeeded" if result.success else "Action failed"
            self._context.append(
                MessageBuilder.create_user_message(
                    text=f"** Action Result **\n\n{result_prefix}: {result.message}"
                )
            )

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
