import ast
import json
import shlex
from pathlib import Path

from cli.automation_cli import build_parser


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "cli" / "coverage_manifest.json"


def test_coverage_manifest_sources_and_commands_exist():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    parser = build_parser()
    seen = set()

    for feature in manifest["features"]:
        source = ROOT / feature["source"]
        assert source.exists(), feature
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for handler in feature["handlers"]:
            assert handler in functions, f"覆盖清单处理函数不存在: {source}:{handler}"
        for command in feature["commands"]:
            parser.parse_args(shlex.split(command))
            seen.add(command.split()[0])

    assert {"status", "task", "config", "device", "diagnostics", "jobs", "mirror", "history", "apps", "build", "paths"} <= seen


def test_every_manifest_feature_has_surface_handler_and_command():
    features = json.loads(MANIFEST.read_text(encoding="utf-8"))["features"]
    assert len(features) >= 25
    assert all(item.get("surface") and item.get("feature") for item in features)
    assert all(item.get("handlers") and item.get("commands") for item in features)


def test_all_page_event_handlers_are_covered_or_explicitly_ui_only():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    covered = {
        (item["source"], handler)
        for item in manifest["features"]
        for handler in item["handlers"]
    }
    excluded = {
        (item["source"], handler)
        for item in manifest["ui_only_handlers"]
        for handler in item["handlers"]
    }
    sources = {
        item["source"]
        for item in manifest["features"] + manifest["ui_only_handlers"]
        if item["source"].startswith("gui/")
    }
    for source in sources:
        tree = ast.parse((ROOT / source).read_text(encoding="utf-8-sig"))
        candidates = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and (node.name.startswith("_on_") or node.name in {"_load_history", "_switch_page"})
        }
        unclassified = {
            handler
            for handler in candidates
            if (source, handler) not in covered and (source, handler) not in excluded
        }
        assert not unclassified, f"未分类的 GUI 事件处理器: {source}: {sorted(unclassified)}"
