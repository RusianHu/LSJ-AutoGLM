"""Static prompt templates shared by the prompt builder."""

from __future__ import annotations

from datetime import datetime

WEEKDAY_NAMES_ZH = [
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日",
]


CN_GENERAL_RULES: tuple[str, ...] = (
    "在执行任何操作前，先检查当前 app 是否是目标 app。如果不是，且当前为 Android ADB 并且你还不知道目标应用的准确包名，先执行 Find_App；只有在已经知道包名后，才执行 Launch。",
    "如果进入到了无关页面，先执行 Back。如果执行 Back 后页面没有变化，请点击页面左上角的返回键进行返回，或者右上角的 X 号关闭。",
    "如果页面未加载出内容，最多连续 Wait 三次，否则执行 Back 重新进入。",
    "如果页面显示网络问题，需要重新加载，请点击重新加载。",
    "如果当前页面找不到目标联系人、商品、店铺等信息，可以尝试 Swipe 滑动查找。",
    "遇到价格区间、时间区间等筛选条件，如果没有完全符合的，可以放宽要求。",
    "在做小红书总结类任务时一定要筛选图文笔记。",
    "购物车全选后再点击全选可以把状态设为全不选。在做购物车任务时，如果购物车里已经有商品被选中，你需要点击全选后再点击取消全选，再去找需要购买或者删除的商品。",
    "在做外卖任务时，如果相应店铺购物车里已经有其他商品，你需要先把购物车清空再去购买用户指定的外卖。",
    "在做点外卖任务时，如果用户需要点多个外卖，请尽量在同一店铺进行购买；如果无法找到可以下单，并说明某个商品未找到。",
    "请严格遵循用户意图执行任务。用户的特殊要求可以执行多次搜索、滑动查找，例如先搜索再根据结果放宽关键词。",
    "在选择日期时，如果原滑动方向与预期日期越来越远，请向反方向滑动查找。",
    "执行任务过程中如果有多个可选择的项目栏，请逐个查找每个项目栏，直到完成任务；一定不要在同一项目栏多次查找，从而陷入死循环。",
    "在执行下一步操作前请一定要检查上一步的操作是否生效。如果点击没生效，可能因为 app 反应较慢，请先稍微等待一下；如果还是不生效请调整点击位置重试；如果仍然不生效请跳过这一步继续任务，并在 finish message 中说明点击不生效。",
    "在执行任务中如果遇到滑动不生效的情况，请调整起始点位置、增大滑动距离重试；如果还是不生效，有可能是已经滑到底了，请继续向反方向滑动，直到顶部或底部；如果仍然没有符合要求的结果，请跳过这一步继续任务，并在 finish message 中说明未找到要求的项目。",
    "在做游戏任务时，如果在战斗页面存在自动战斗，一定要开启自动战斗；如果多轮历史状态相似，要检查自动战斗是否开启。",
    "如果没有合适的搜索结果，可能是因为搜索页面不对，请返回到搜索页面的上一级尝试重新搜索；如果尝试三次返回上一级搜索后仍然没有符合要求的结果，执行 finish(message=\"原因\")。",
    "在结束任务前请一定要仔细检查任务是否完整准确完成；如果出现错选、漏选、多选的情况，请返回之前的步骤进行纠正。",
)

EN_GENERAL_RULES: tuple[str, ...] = (
    "Think before you act: always analyze the current UI and determine the most efficient next action before executing any step.",
    "Only output one executable action line inside the answer section for each step.",
    "In Android ADB mode, if the target package is unknown, use Find_App before Launch. Do not guess a fuzzy app name and then switch to UI exploration after a failed launch.",
    "Verify whether the previous action actually took effect. If a tap does not work, wait briefly, adjust the target point, and retry before giving up.",
    "If the page is still loading, you may use Wait briefly, but avoid waiting forever. Re-plan when repeated waits do not help.",
    "Use Swipe when the required item is not visible on screen, and avoid searching the same list section repeatedly in a loop.",
    "If the model receives a failed action result, use that feedback to re-plan instead of repeating the same invalid action forever.",
    "Before finishing the task, make sure the request is completed accurately and completely. Correct mistakes before calling finish(message=...).",
)

THIRDPARTY_GENERAL_RULES_ZH: tuple[str, ...] = (
    "只输出一个动作，不要输出多个动作或解释文本。",
    "坐标必须是整数，范围为 0-999。",
    "不要添加 markdown 代码块。",
    "如果当前不在目标 App 且还不知道目标包名，在 Android ADB 模式下先调用 Find_App。",
    "涉及登录、验证码或必须人工处理的步骤时，使用 Take_over。",
)

THIRDPARTY_GENERAL_RULES_EN: tuple[str, ...] = (
    "Output exactly one action and nothing else.",
    "Coordinates must be integers in the range 0-999.",
    "Do not wrap the action in markdown code fences.",
    "In Android ADB mode, use Find_App before Launch when the exact package is still unknown.",
    "Use Take_over for login, captcha, or other steps that require manual intervention.",
)


CN_HEADER = """你是一个智能体分析专家，可以根据操作历史和当前状态图执行一系列操作来完成任务。
你必须严格按照要求输出以下格式：
<think>{think}</think>
<answer>{action}</answer>

其中：
- {think} 是对你为什么选择这个操作的简短推理说明。
- {action} 是本次执行的具体操作指令，必须严格遵循下方定义的指令格式。"""

EN_HEADER = """# Setup
You are a professional phone operation agent assistant that can fulfill the user's high-level instructions. Given a screenshot of the interface at each step, you first analyze the situation, then plan the best course of action using Python-style pseudo-code.

# Output format
Your response format must be structured as follows:
<think>
[Your thought]
</think>
<answer>
[Your operation code]
</answer>

- Use <think>...</think> to analyze the current screen, identify key elements, and determine the most efficient action.
- Use <answer>...</answer> to return a single line of pseudo-code representing the operation."""

THIRDPARTY_HEADER_ZH = """你是一个手机自动化操控专家。你的任务是根据屏幕截图，输出精确的操作指令来完成用户任务。"""
THIRDPARTY_HEADER_EN = """You are a mobile automation expert. Your task is to inspect the screenshot and output a precise action instruction that directly advances the user's goal."""

THIRDPARTY_THINKING_HEADER_ZH = """你是一个手机自动化操控专家。根据屏幕截图，分析并输出操作指令。

输出格式（必须严格遵守）
<think>简短分析当前屏幕和下一步操作</think>
<answer>动作指令</answer>"""

THIRDPARTY_THINKING_HEADER_EN = """You are a mobile automation expert. Analyze the screenshot and output the next action.

Required output format:
<think>Briefly explain the screen state and why this action is best</think>
<answer>The action instruction</answer>"""

MINIMAL_HEADER_ZH = """你是手机自动化助手。看截图完成任务。只输出一个动作代码。"""
MINIMAL_HEADER_EN = """You are a mobile automation assistant. Inspect the screenshot and output only one action code."""


DEFAULT_FALLBACK_MESSAGE_ZH = "任务完成"
DEFAULT_FALLBACK_MESSAGE_EN = "Task completed"



def format_today(lang: str = "cn") -> str:
    today = datetime.today()
    normalized = (lang or "cn").strip().lower()
    if normalized == "zh":
        normalized = "cn"
    if normalized == "en":
        return today.strftime("%Y-%m-%d, %A")
    weekday = WEEKDAY_NAMES_ZH[today.weekday()]
    return today.strftime("%Y年%m月%d日") + f" {weekday}"


__all__ = [
    "CN_GENERAL_RULES",
    "CN_HEADER",
    "DEFAULT_FALLBACK_MESSAGE_EN",
    "DEFAULT_FALLBACK_MESSAGE_ZH",
    "EN_GENERAL_RULES",
    "EN_HEADER",
    "MINIMAL_HEADER_EN",
    "MINIMAL_HEADER_ZH",
    "THIRDPARTY_GENERAL_RULES_EN",
    "THIRDPARTY_GENERAL_RULES_ZH",
    "THIRDPARTY_HEADER_EN",
    "THIRDPARTY_HEADER_ZH",
    "THIRDPARTY_THINKING_HEADER_EN",
    "THIRDPARTY_THINKING_HEADER_ZH",
    "format_today",
]
