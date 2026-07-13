# -*- coding: utf-8 -*-
"""检查 GUI 与 Phone Agent 的 i18n 资源完整性。

检查内容：
* 语言词典是否可解析、是否存在重复键或空文案；
* 中英文键集合是否完全一致；
* ``str.format`` 占位符签名是否一致；
* 代码中的静态 i18n 引用是否都能解析；
* 动作注册表生成的动态键是否都已翻译；
* 使用 Aho–Corasick 一次扫描所有源码中的已知键，避免逐键逐文件匹配。

该脚本只依赖 Python 标准库和项目自身的动作注册表，可直接用于 CI。
"""

from __future__ import annotations

import ast
import re
import string
import sys
from collections import Counter, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
_I18N_CALLS = {"t", "_t", "get_message"}
_I18N_KEY_KWARGS = {
    "i18n_key",
    "message_key",
    "label_i18n_key",
    "description_i18n_key",
    "hint_i18n_key",
    "category_i18n_key",
    "risk_i18n_key",
    "label_key",
    "detail_key",
    "hint_key",
    "title_key",
    "action_hint_key",
}
_SKIP_PARTS = {"venv", "build", "dist", "__pycache__"}


@dataclass
class Catalog:
    path: Path
    name: str
    values: dict[str, str] = field(default_factory=dict)
    duplicate_keys: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class CheckReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    catalog_sizes: dict[str, int] = field(default_factory=dict)
    static_refs: set[str] = field(default_factory=set)
    dynamic_refs: set[str] = field(default_factory=set)
    matched_occurrences: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def _find_dict_node(tree: ast.AST, name: str) -> ast.Dict | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return node.value if isinstance(node.value, ast.Dict) else None
    return None


def load_catalog(path: Path, name: str) -> Catalog:
    catalog = Catalog(path=path, name=name)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        catalog.errors.append(f"{path}: 无法解析词典: {exc}")
        return catalog

    node = _find_dict_node(tree, name)
    if node is None:
        catalog.errors.append(f"{path}: 未找到字典 {name}")
        return catalog

    seen: set[str] = set()
    for key_node, value_node in zip(node.keys, node.values):
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            catalog.errors.append(f"{path}:{getattr(key_node, 'lineno', '?')}: 键必须是字符串")
            continue
        key = key_node.value
        if key in seen:
            catalog.duplicate_keys.append(key)
        seen.add(key)
        if not isinstance(value_node, ast.Constant) or not isinstance(value_node.value, str):
            catalog.errors.append(f"{path}:{getattr(value_node, 'lineno', '?')}: {key} 的文案必须是字符串")
            continue
        if not value_node.value.strip():
            catalog.errors.append(f"{path}:{getattr(value_node, 'lineno', '?')}: {key} 的文案为空")
        catalog.values[key] = value_node.value
    return catalog


def _format_fields(template: str) -> tuple[str, ...]:
    fields: list[str] = []
    try:
        for _, field_name, _, _ in string.Formatter().parse(template):
            if field_name:
                fields.append(field_name)
    except ValueError as exc:
        return (f"<FORMAT_ERROR:{exc}>",)
    return tuple(fields)


class AhoCorasick:
    """无第三方依赖的多模式匹配器，扫描复杂度为 O(文本长度 + 匹配数)。"""

    def __init__(self, patterns: Iterable[str]):
        self._next: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._out: list[list[str]] = [[]]
        for pattern in sorted(set(patterns)):
            state = 0
            for char in pattern:
                child = self._next[state].get(char)
                if child is None:
                    child = len(self._next)
                    self._next[state][char] = child
                    self._next.append({})
                    self._fail.append(0)
                    self._out.append([])
                state = child
            self._out[state].append(pattern)

        queue: deque[int] = deque()
        for state in self._next[0].values():
            queue.append(state)
        while queue:
            state = queue.popleft()
            for char, child in self._next[state].items():
                queue.append(child)
                fallback = self._fail[state]
                while fallback and char not in self._next[fallback]:
                    fallback = self._fail[fallback]
                self._fail[child] = self._next[fallback].get(char, 0)
                self._out[child].extend(self._out[self._fail[child]])

    def find(self, text: str) -> Iterable[str]:
        state = 0
        for char in text:
            while state and char not in self._next[state]:
                state = self._fail[state]
            state = self._next[state].get(char, 0)
            yield from self._out[state]


def _source_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part in _SKIP_PARTS for part in path.parts):
            continue
        if path.parts[-3:-1] == ("i18n", "locales"):
            continue
        yield path


def _static_references(
    path: Path,
) -> tuple[set[str], list[str], list[tuple[str, Path, int, set[str], bool]]]:
    refs: set[str] = set()
    errors: list[str] = []
    format_calls: list[tuple[str, Path, int, set[str], bool]] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return refs, [f"{path}: 无法解析源码: {exc}"], format_calls

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function_name = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            message_key = next(
                (
                    keyword.value.value
                    for keyword in node.keywords
                    if keyword.arg == "message_key"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                    and _KEY_RE.fullmatch(keyword.value.value)
                ),
                None,
            )
            if message_key:
                refs.add(message_key)
                message_params = next(
                    (
                        keyword.value
                        for keyword in node.keywords
                        if keyword.arg == "message_params"
                    ),
                    None,
                )
                if isinstance(message_params, ast.Dict):
                    provided = {
                        key.value
                        for key in message_params.keys
                        if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    }
                    format_calls.append((message_key, path, node.lineno, provided, False))
            if function_name in _I18N_CALLS and node.args:
                argument = node.args[0]
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    if _KEY_RE.fullmatch(argument.value):
                        refs.add(argument.value)
                        if function_name in {"t", "_t"}:
                            provided = {
                                keyword.arg
                                for keyword in node.keywords
                                if keyword.arg and keyword.arg not in _I18N_KEY_KWARGS
                            }
                            has_unpack = any(keyword.arg is None for keyword in node.keywords)
                            format_calls.append(
                                (argument.value, path, node.lineno, provided, has_unpack)
                            )
            for keyword in node.keywords:
                if keyword.arg not in _I18N_KEY_KWARGS:
                    continue
                if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    if _KEY_RE.fullmatch(keyword.value.value):
                        refs.add(keyword.value.value)
    return refs, errors, format_calls


def _dynamic_registry_keys() -> set[str]:
    """读取动作注册表，覆盖运行时拼出的 action.* 键。"""
    sys.path.insert(0, str(ROOT))
    from phone_agent.actions.registry import CATEGORY_I18N_KEYS, get_all_action_specs

    keys = set(CATEGORY_I18N_KEYS.values())
    specs = get_all_action_specs()
    keys.update(f"action.risk.{spec.risk_level}" for spec in specs)
    for spec in specs:
        keys.update(
            {
                spec.label_i18n_key,
                spec.description_i18n_key,
                spec.hint_i18n_key,
            }
        )
    return keys


def run_checks(root: Path = ROOT) -> CheckReport:
    report = CheckReport()
    catalogs = {
        "gui.cn": load_catalog(root / "gui/i18n/locales/cn.py", "CN"),
        "gui.en": load_catalog(root / "gui/i18n/locales/en.py", "EN"),
        "agent.cn": load_catalog(root / "phone_agent/config/i18n.py", "MESSAGES_ZH"),
        "agent.en": load_catalog(root / "phone_agent/config/i18n.py", "MESSAGES_EN"),
    }
    for label, catalog in catalogs.items():
        report.catalog_sizes[label] = len(catalog.values)
        report.errors.extend(catalog.errors)
        report.errors.extend(f"{catalog.path}: 重复键 {key}" for key in catalog.duplicate_keys)

    gui_cn = catalogs["gui.cn"].values
    gui_en = catalogs["gui.en"].values
    agent_cn = catalogs["agent.cn"].values
    agent_en = catalogs["agent.en"].values
    for label, left, right in (
        ("GUI", gui_cn, gui_en),
        ("Phone Agent", agent_cn, agent_en),
    ):
        for key in sorted(set(left) - set(right)):
            report.errors.append(f"{label}: {key} 仅存在于中文词典")
        for key in sorted(set(right) - set(left)):
            report.errors.append(f"{label}: {key} 仅存在于英文词典")
        for key in sorted(set(left) & set(right)):
            left_fields = _format_fields(left[key])
            right_fields = _format_fields(right[key])
            if left_fields != right_fields:
                report.errors.append(
                    f"{label}: {key} 占位符不一致: {left_fields!r} != {right_fields!r}"
                )

    all_keys = set(gui_cn) | set(gui_en) | set(agent_cn) | set(agent_en)
    automaton = AhoCorasick(all_keys)
    for path in _source_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            report.errors.append(f"{path}: 无法读取源码: {exc}")
            continue
        report.matched_occurrences += sum(1 for _ in automaton.find(text))
        refs, errors, format_calls = _static_references(path)
        report.static_refs.update(refs)
        report.errors.extend(errors)
        for key, source_path, line, provided, has_unpack in format_calls:
            template = gui_cn.get(key) or agent_cn.get(key)
            if template is None or has_unpack:
                continue
            required = {
                field_name
                for field_name in _format_fields(template)
                if not field_name.startswith("<FORMAT_ERROR:")
            }
            missing = sorted(required - provided)
            if missing:
                report.errors.append(
                    f"{source_path}:{line}: {key} 缺少格式化参数: {', '.join(missing)}"
                )

    known_keys = set(gui_cn) | set(gui_en) | set(agent_cn) | set(agent_en)
    for key in sorted(report.static_refs - known_keys):
        report.errors.append(f"源码引用了缺失 i18n 键: {key}")

    try:
        report.dynamic_refs = _dynamic_registry_keys()
    except Exception as exc:  # pragma: no cover - 仅在项目依赖损坏时触发
        report.errors.append(f"无法读取动作注册表动态键: {exc}")
    for key in sorted(report.dynamic_refs - set(gui_cn) - set(gui_en)):
        report.errors.append(f"动态动作键缺失于 GUI 词典: {key}")

    used = report.static_refs | report.dynamic_refs
    unused_gui = sorted(set(gui_cn) - used)
    if unused_gui:
        report.warnings.append(
            f"GUI 词典有 {len(unused_gui)} 个当前未被静态/注册表引用的键（允许历史兼容键存在）"
        )
    return report


def main() -> int:
    report = run_checks()
    print("i18n 完整性检查")
    print("词典数量: " + ", ".join(f"{key}={size}" for key, size in sorted(report.catalog_sizes.items())))
    print(f"Aho–Corasick 源码匹配: {report.matched_occurrences} 次")
    if report.warnings:
        for warning in report.warnings:
            print(f"警告: {warning}")
    if report.errors:
        print(f"失败: {len(report.errors)} 项")
        for error in report.errors:
            print(f"- {error}")
        return 1
    print("通过: 键集合、占位符、静态引用和动态动作键均一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
