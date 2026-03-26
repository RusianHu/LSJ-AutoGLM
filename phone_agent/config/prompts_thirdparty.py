"""第三方模型提示词兼容层。"""

from __future__ import annotations

from phone_agent.actions.registry import ActionPolicyInput
from phone_agent.prompts import build_system_prompt



def get_thirdparty_system_prompt(
    *,
    lang: str = "cn",
    platform: str | None = None,
    thinking: bool = False,
    minimal: bool = False,
    action_policy: ActionPolicyInput | None = None,
) -> str:
    return build_system_prompt(
        lang=lang,
        platform=platform,
        thirdparty=True,
        thinking=thinking,
        minimal=minimal,
        action_policy=action_policy,
    )


ACTION_FORMAT_GUIDE = get_thirdparty_system_prompt(thinking=False)
THIRDPARTY_SYSTEM_PROMPT = get_thirdparty_system_prompt(thinking=False)
THIRDPARTY_SYSTEM_PROMPT_WITH_THINKING = get_thirdparty_system_prompt(thinking=True)
THIRDPARTY_SIMPLE_PROMPT = get_thirdparty_system_prompt(thinking=True)
THIRDPARTY_MINIMAL_PROMPT = get_thirdparty_system_prompt(thinking=False, minimal=True)
THIRDPARTY_MINIMAL_PROMPT_WITH_THINKING = get_thirdparty_system_prompt(
    thinking=True,
    minimal=True,
)

FEW_SHOT_EXAMPLES = [
    {
        "task": "查找设置的包名",
        "screen_desc": "手机主屏幕，显示多个应用图标",
        "output": 'do(action="Find_App", query="settings")',
    },
    {
        "task": "点击发现按钮",
        "screen_desc": "微信主界面，底部有4个标签：微信、通讯录、发现、我",
        "output": 'do(action="Tap", element=[625, 950])',
    },
    {
        "task": "向下滑动查看更多",
        "screen_desc": "商品列表页面",
        "output": 'do(action="Swipe", start=[500, 800], end=[500, 200])',
    },
    {
        "task": "搜索耳机",
        "screen_desc": "搜索框已激活，光标闪烁",
        "output": 'do(action="Type", text="耳机")',
    },
    {
        "task": "返回上一页",
        "screen_desc": "商品详情页",
        "output": 'do(action="Back")',
    },
]



def build_thirdparty_messages(
    task: str,
    image_base64: str,
    history: list | None = None,
    use_thinking: bool = True,
    embed_in_user: bool = True,
    *,
    lang: str = "cn",
    platform: str | None = None,
    minimal: bool = False,
    action_policy: ActionPolicyInput | None = None,
) -> list:
    """构建第三方模型消息列表。"""
    system_prompt = get_thirdparty_system_prompt(
        lang=lang,
        platform=platform,
        thinking=use_thinking,
        minimal=minimal,
        action_policy=action_policy,
    )

    messages = []

    task_text = f"任务: {task}"
    if history:
        history_text = "\n".join([f"步骤{i + 1}: {h}" for i, h in enumerate(history[-5:])])
        task_text = f"任务: {task}\n\n历史操作:\n{history_text}\n\n请根据当前屏幕输出下一步操作:"

    if embed_in_user:
        combined_text = f"{system_prompt}\n\n---\n{task_text}"
        user_content = [
            {"type": "text", "text": combined_text},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "system", "content": system_prompt})
        user_content = [
            {"type": "text", "text": task_text},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
        ]
        messages.append({"role": "user", "content": user_content})

    return messages
