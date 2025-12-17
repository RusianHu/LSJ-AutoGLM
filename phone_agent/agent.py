"""Main PhoneAgent class for orchestrating phone automation."""

import json
import traceback
from collections import deque
from dataclasses import dataclass
from hashlib import sha1
from typing import Any, Callable

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder


@dataclass
class AgentConfig:
    """Configuration for the PhoneAgent."""

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True
    use_thirdparty_prompt: bool = False  # 使用第三方模型提示词
    thirdparty_thinking: bool = True  # 第三方模式也使用 <think>/<answer> 规范输出

    def __post_init__(self):
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(
                self.lang,
                self.use_thirdparty_prompt,
                thirdparty_thinking=self.thirdparty_thinking,
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
        self.action_handler = ActionHandler(
            device_id=self.agent_config.device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0
        self._last_screen_hash: str | None = None
        self._screen_unchanged_steps = 0
        self._recent_action_signatures: deque[str] = deque(maxlen=12)
        self._stuck_warnings = 0

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
        self._last_screen_hash = None
        self._screen_unchanged_steps = 0
        self._recent_action_signatures.clear()
        self._stuck_warnings = 0

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

        # If we're clearly stuck for a long time, force a manual takeover to avoid burning steps.
        if (
            self.agent_config.use_thirdparty_prompt
            and self._screen_unchanged_steps >= 6
            and self._stuck_warnings >= 2
        ):
            action = do(
                action="Take_over",
                message="检测到长时间无界面变化且动作可能循环，请手动进入目标页面（例如 QQ 钱包/余额页），完成后按回车继续。",
            )
            result = self.action_handler.execute(action, screenshot.width, screenshot.height)
            return StepResult(
                success=result.success,
                finished=result.should_finish,
                action=action,
                thinking="",
                message=result.message,
            )

        # Build messages
        if is_first:
            screen_info = MessageBuilder.build_screen_info(current_app)

            if self.agent_config.use_thirdparty_prompt:
                # 第三方模型：将系统提示词嵌入用户消息（某些 API 不支持 system role）
                text_content = f"{self.agent_config.system_prompt}\n\n---\n任务: {user_prompt}\n\n{screen_info}"
                self._context.append(
                    MessageBuilder.create_user_message(
                        text=text_content, image_base64=screenshot.base64_data
                    )
                )
            else:
                # 标准模式：使用 system role
                self._context.append(
                    MessageBuilder.create_system_message(self.agent_config.system_prompt)
                )
                text_content = f"{user_prompt}\n\n{screen_info}"
                self._context.append(
                    MessageBuilder.create_user_message(
                        text=text_content, image_base64=screenshot.base64_data
                    )
                )
        else:
            screen_info = MessageBuilder.build_screen_info(current_app)

            if self.agent_config.use_thirdparty_prompt:
                # 第三方模型：显式给出最近动作，且在卡住时要求改变策略/请求接管
                recent = list(self._recent_action_signatures)[-6:]
                history_text = "\n".join([f"- {s}" for s in recent]) if recent else "(无)"

                stuck_hints = ""
                is_loop = self._looks_like_loop(list(self._recent_action_signatures))
                if self._screen_unchanged_steps >= 2 or is_loop:
                    self._stuck_warnings += 1
                    stuck_hints = (
                        "\n\n你可能卡住了（界面长时间未变化或动作重复）。"
                        "请改变策略：例如先确保在 QQ 的“我的/个人中心”页，再进入“钱包/余额”；"
                        "必要时可尝试下拉/搜索；如需登录/验证码请输出："
                        'do(action="Take_over", message="需要你手动登录/验证")。'
                    )

                tail_instruction = (
                    "按规范输出 <think>/<answer>（think 尽量简短），每步只输出一个动作。"
                    if self.agent_config.thirdparty_thinking
                    else "只输出一个动作代码，不要解释。"
                )
                text_content = (
                    f"继续执行任务。当前屏幕信息：{screen_info}\n\n"
                    f"最近动作(供参考)：\n{history_text}"
                    f"{stuck_hints}\n\n"
                    f"{tail_instruction}"
                )
            else:
                text_content = f"** Screen Info **\n\n{screen_info}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=screenshot.base64_data
                )
            )

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
        if self.agent_config.use_thirdparty_prompt:
            if self.agent_config.thirdparty_thinking:
                self._context.append(
                    MessageBuilder.create_assistant_message(
                        f"<think>{response.thinking}</think><answer>{response.action}</answer>"
                    )
                )
            else:
                # 第三方模型：不使用 XML 标签，直接输出动作
                self._context.append(MessageBuilder.create_assistant_message(response.action))
        else:
            self._context.append(
                MessageBuilder.create_assistant_message(
                    f"<think>{response.thinking}</think><answer>{response.action}</answer>"
                )
            )

        # Parse action from response (retry once for thirdparty models)
        parse_error: Exception | None = None
        action: dict[str, Any] | None = None
        for attempt in range(2):
            try:
                action = parse_action(response.action)
                parse_error = None
                break
            except ValueError as e:
                parse_error = e
                if self.agent_config.verbose:
                    traceback.print_exc()

                # Thirdparty models are more likely to produce slightly malformed action code.
                # Ask the model to re-output a strictly valid action once.
                if attempt == 0 and self.agent_config.use_thirdparty_prompt:
                    retry_text = (
                        "上一步输出的动作代码无法解析。\n"
                        f"原始输出: {response.action}\n"
                        f"解析错误: {e}\n\n"
                        "请重新输出。优先按规范使用 <think>/<answer>，但必须保证动作可解析；"
                        "如果不支持 XML 标签，则直接输出 1 行动作代码。\n"
                        "示例：\n"
                        "<think>点击搜索</think><answer>do(action=\"Tap\", element=[500, 500])</answer>\n"
                        "或\n"
                        "finish(message=\"任务完成\")"
                    )
                    self._context.append(
                        MessageBuilder.create_user_message(text=retry_text, image_base64=None)
                    )
                    response = self.model_client.request(self._context)

                    # Append the retry assistant output too
                    if self.agent_config.use_thirdparty_prompt:
                        if self.agent_config.thirdparty_thinking:
                            self._context.append(
                                MessageBuilder.create_assistant_message(
                                    f"<think>{response.thinking}</think><answer>{response.action}</answer>"
                                )
                            )
                        else:
                            self._context.append(
                                MessageBuilder.create_assistant_message(response.action)
                            )
                    else:
                        self._context.append(
                            MessageBuilder.create_assistant_message(
                                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
                            )
                        )
                    continue
                break

        if action is None:
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking=response.thinking,
                message=f"动作解析失败，无法继续执行：{parse_error}",
            )

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
