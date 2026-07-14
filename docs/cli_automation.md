# 自动化控制 CLI

`open-autoglm` 是面向 Codex、Claude Code、CI 和脚本的统一控制入口。它覆盖 TUI/GUI 的后端功能，默认输出 JSON，且不会进入交互菜单。

源码仓库内可使用 `python cli_app.py`；执行 `pip install -e .` 后也可使用 `open-autoglm`。两者参数完全一致。

## 稳定约定

- 默认输出为 `{"ok": bool, "message": str, "data": ...}`；使用 `--format text` 可切换为文本。
- `task start`、`diagnostics start`、`mirror start`、`config test-api`、`device qr-start`、`build gui` 会立即返回 `job_id`。
- 后台作业通过后续 CLI 调用执行 `status`、`logs`、`pause`、`resume`、`stop` 或 `wait`，不依赖启动它的终端继续存在。
- GUI 启动的 Agent 任务也会注册为 `owner=gui` 的作业；可用 `task list` 找到并由 CLI 暂停、恢复、停止或追加指令，GUI 会同步显示外部状态变化。
- `task run`、`task wait` 和 `diagnostics run` 是显式同步命令，均有超时参数。
- API Key 默认遮罩；只有 `config get/list --show-secrets` 会输出明文。
- 全局参数必须放在子命令之前，例如 `open-autoglm --env-file .env config list`。

退出码：`0` 成功、`1` 执行失败、`2` 参数错误、`3` 目标不存在、`4` 状态冲突、`5` 超时。

## 能力发现与状态

```powershell
python cli_app.py capabilities
python cli_app.py status --probe-devices
python cli_app.py paths
python cli_app.py --help
```

`capabilities` 返回机器可读覆盖矩阵，自动化工具应优先用它发现能力。

仓库内的 `cli/coverage_manifest.json` 是可执行覆盖清单：它把 TUI/GUI 的用户动作、源事件处理函数和 CLI 命令逐项绑定。测试会解析源代码与完整命令树，任何处理函数被删除、改名或命令失效都会导致测试失败。

## 非阻塞任务生命周期

```powershell
$started = python cli_app.py task start "打开设置并报告系统版本" | ConvertFrom-Json
$job = $started.data.job_id

python cli_app.py task status $job
python cli_app.py task logs $job --lines 100
python cli_app.py task instruct $job "先检查网络设置"
python cli_app.py task pause $job
python cli_app.py task resume $job
python cli_app.py task takeover $job --reason "需要人工确认"
python cli_app.py task stop $job
```

任务日志、运行时 inbox、作业状态和 GUI 兼容历史默认位于 `gui_history/`。可用 `--state-dir` 或 `OPEN_AUTOGLM_CLI_STATE_DIR` 隔离测试运行。

## 配置与渠道

```powershell
python cli_app.py config list
python cli_app.py config get OPEN_AUTOGLM_MODEL
python cli_app.py config set OPEN_AUTOGLM_LANG en
python cli_app.py config set-many '{"OPEN_AUTOGLM_MAX_STEPS":"60","OPEN_AUTOGLM_THEME":"dark"}'
python cli_app.py config validate
python cli_app.py config channels
python cli_app.py config use-channel modelscope
python cli_app.py config swap-keys

python cli_app.py config action-policy --platform adb --select-all
python cli_app.py config action-policy --clear
python cli_app.py config mirror-toolbar --enabled true --select-all

$check = python cli_app.py config test-api | ConvertFrom-Json
python cli_app.py config api-result $check.data.job_id
```

配置命令与 GUI 共用 `.env` 和 `ConfigService` 的校验、渠道解析、动作策略解析及原子写入逻辑。

## 设备、配对和应用

```powershell
python cli_app.py device list
python cli_app.py device select 77eaf689
python cli_app.py device connect-start 192.168.1.20:38123
python cli_app.py device pair-start 192.168.1.20:42001 123456
python cli_app.py device tcpip-start 77eaf689 --port 5555
python cli_app.py device usb-start 77eaf689
python cli_app.py device ip 77eaf689
python cli_app.py device keyboard-status 77eaf689
python cli_app.py device install-keyboard-start 77eaf689
python cli_app.py device restart-adb

python cli_app.py device qr --output gui_history/pairing.png
$pair = python cli_app.py device qr-start studio-xxxx password --pair-timeout 90 | ConvertFrom-Json
python cli_app.py jobs status $pair.data.job_id
python cli_app.py jobs stop $pair.data.job_id

python cli_app.py apps supported --platform adb
python cli_app.py apps device --device-id 77eaf689
python cli_app.py apps find wechat --device-id 77eaf689
```

不带 `-start` 的 `connect`、`pair`、`tcpip`、`usb`、`disconnect` 和 `install-keyboard` 是有超时上限的同步版本，主要供人工一次性调用；自动化工具应优先使用后台版本。

iOS 可使用 `device list --platform ios`、`device ios-pair` 与 `device wda-status`；HarmonyOS 可使用 `device list --platform hdc`。

## 诊断、历史、镜像与构建

```powershell
$diag = python cli_app.py diagnostics start | ConvertFrom-Json
python cli_app.py diagnostics result $diag.data.job_id

python cli_app.py history list
python cli_app.py history show TASK_ID
python cli_app.py history logs TASK_ID

$mirror = python cli_app.py mirror start 77eaf689 --mode auto | ConvertFrom-Json
python cli_app.py mirror action home --job-id $mirror.data.job_id
python cli_app.py mirror screenshot --job-id $mirror.data.job_id
python cli_app.py mirror paste --job-id $mirror.data.job_id
python cli_app.py mirror stop --job-id $mirror.data.job_id

$build = python cli_app.py build gui | ConvertFrom-Json
python cli_app.py build logs $build.data.job_id
python cli_app.py build stop $build.data.job_id
```

镜像的 `auto` 模式优先启动 scrcpy 独立窗口；找不到 scrcpy 时会启动可停止的 ADB 截图轮询，并在作业状态中返回 `latest_frame`。这与 GUI 的降级语义一致，但不尝试把原生窗口嵌入或动态 reparent 到其他宿主。
