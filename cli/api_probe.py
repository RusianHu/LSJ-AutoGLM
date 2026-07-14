# -*- coding: utf-8 -*-
"""隔离执行模型 API 实连测试，便于父作业随时终止。"""

from __future__ import annotations

import argparse
from pathlib import Path

from cli.system_checks import check_model_api
from gui.services.config_service import ConfigService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default="")
    args = parser.parse_args(argv)
    config = ConfigService(env_file=Path(args.env_file) if args.env_file else None)
    api_key, _ = config.resolve_api_key()
    ok = check_model_api(
        config.get("OPEN_AUTOGLM_BASE_URL"),
        config.get("OPEN_AUTOGLM_MODEL"),
        api_key or "EMPTY",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

