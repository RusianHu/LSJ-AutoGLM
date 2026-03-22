# GUI i18n Spec / Phase Todo

## Context
当前项目的 GUI 文案主要分散硬编码在 `gui/main_window.py`、`gui/pages/*`、`gui/services/*` 中，界面层尚未形成统一 i18n 机制；但运行链路已经存在 `OPEN_AUTOGLM_LANG -> gui/services/config_service.py -> main.py --lang` 的传递能力，说明“界面语言”和“任务运行语言”可以共用单一配置源。

本次变更的目标，是在**仅支持简体中文 / 英文**的前提下，为 GUI 建立一套可维护、可逐页扩展、可即时全局切换的 i18n 方案，并产出一份可直接执行的规范。该方案要覆盖：
- 基础界面文案
- 运行反馈 / 弹窗 / 环境摘要
- 历史事件展示

同时遵循本次已确认的产品约束：
- 使用同一个 `OPEN_AUTOGLM_LANG` 同时驱动 GUI 语言和后续新任务的运行语言
- 语言切换入口仅放在设置页
- 保存后 GUI 立即全局切换
- **当前正在运行的任务进程不重启**，其运行语言保持启动时值；下一次启动任务才使用新语言
- 历史记录**旧内容不重渲**，仅新内容按新语言保存
- 原始日志 / traceback / 第三方输出**不做翻译**，只翻译事件层与 GUI 摘要层
- 缺词时**显式暴露 key**，便于测试阶段发现漏项
- 英文文案风格采用**开发者工具风**（简洁、直接、技术导向）
- 未来第三语言只做**轻度预留**，不为一期增加额外复杂度

---

## Locked Decisions
- [x] GUI 语言与任务运行语言第一期先统一，共用 `OPEN_AUTOGLM_LANG`
- [x] 语言切换为“即时全局”
- [x] 第一阶段必须覆盖：基础界面、运行反馈、历史事件
- [x] 历史记录切换语言后仅影响新内容，旧历史保留原语种
- [x] 运行中切换语言时：GUI 立即切换，当前运行任务不重启
- [x] 历史数据演进采用“仅新记录升级”，不做一次性迁移
- [x] 语言切换入口仅放在设置页
- [x] 英文风格采用开发者工具风
- [x] 未来第三语言仅轻度预留
- [x] 缺词回退策略为“显式暴露 key”
- [x] 原始日志不翻译，只翻译事件层 / 摘要层
- [x] 最终规范粒度采用“架构 + 阶段 + 页面/服务覆盖矩阵”

---

## Scope

### In Scope
- [ ] 主窗口壳层：窗口标题、导航、全局弹窗
- [ ] 设置页：语言切换入口、字段标签、校验横幅、保存反馈
- [ ] 工作台：工具栏、状态条、环境摘要条、结果摘要、事件时间线
- [ ] 历史页：筛选器、标签页、状态标签、概览字段、事件列表
- [ ] 设备页：静态界面文案、配对/连接类对话框与反馈文案
- [ ] 诊断页：页内说明、结果格式化、摘要信息
- [ ] 运行反馈：`TaskService` 事件文案、`ReadinessService` 检查 label/detail/hint
- [ ] 历史持久化：新事件保存 `lang / message_key / message_params / rendered_message`
- [ ] 配置联动：继续复用 `OPEN_AUTOGLM_LANG` 与 `main.py --lang`

### Out of Scope
- [ ] 原始 stdout/stderr/traceback 翻译
- [ ] 第三语言支持
- [ ] 主窗口额外快捷切换入口
- [ ] 对旧历史记录做批量迁移
- [ ] 全 CLI 文案体系重构
- [ ] 引入 Qt `.ts/.qm` / Linguist 流程

---

## Existing Code to Reuse

### 1. 配置与运行语言链路
- `gui/services/config_service.py`
  - `get()` / `set()` / `set_many()` / `validate()`
  - `build_command_args()` 已把 `OPEN_AUTOGLM_LANG` 透传到 `main.py --lang`
  - `config_changed` / `config_saved` / `config_error` 现成可复用
- `main.py`
  - `parse_args()` 已支持 `--lang {cn,en}`
  - `ModelConfig` / `AgentConfig` 已消费 `lang`
- `.env.example`
  - 已存在 `OPEN_AUTOGLM_LANG=cn`

### 2. 全局广播范式
- `gui/theme/manager.py`
  - 单一权威管理器 + `theme_changed` 广播
- `gui/theme/page_adapter.py`
  - 注册页面并统一分发，兼容新旧接口

### 3. 运行反馈与历史链路
- `gui/services/task_service.py`
  - `_add_event()`、`_infer_events_from_log()`、`task_finished` 是事件生成主入口
- `gui/services/history_service.py`
  - `save_record()`、`_normalize_record()`、`get_record()`、`get_events()` 是历史序列化主入口
- `gui/services/readiness_service.py`
  - `ReadinessCheckResult`、`ReadinessSummary`
  - `run_readiness_checks()` / `summarize_readiness()` / `collect_blocking_labels()`

### 4. 既有 i18n 参考（仅作模式参考）
- `phone_agent/config/i18n.py`
  - 已使用 key -> 文案 的中英字典模式，可借鉴 `get_message()` 的轻量思路

### 5. 现有测试基线
- `tests/test_theme_engine.py`
  - 可作为 `I18nManager` / `PageI18nAdapter` 单元测试风格参考

---

## Recommended Architecture

### 方案：轻量自研 GUI i18n 总线
采用与 ThemeEngine 平行的轻量架构，而非引入 Qt Linguist：

#### A. `I18nManager`（新增）
建议新增：
- `gui/i18n/manager.py`

职责：
- [ ] 持有当前 GUI 语言（`cn` / `en`，并兼容 `zh -> cn`）
- [ ] 提供 `set_language()` / `get_language()` / `t(key, **params)`
- [ ] 维护当前词典，并发出 `language_changed` 信号
- [ ] 缺词时返回显式占位，例如 `[[page.dashboard.btn.start]]`
- [ ] 记录缺词日志，便于补齐

#### B. `PageI18nAdapter`（新增）
建议新增：
- `gui/i18n/page_adapter.py`

职责：
- [ ] 参考 `gui/theme/page_adapter.py`，由 `MainWindow` 统一注册各页面
- [ ] 监听 `I18nManager.language_changed`
- [ ] 优先调用页面新接口（如 `apply_i18n(i18n_manager)` / `retranslate_ui()`）
- [ ] 为迁移期保留兼容层，避免一次性重写全部页面

#### C. 词典组织（新增）
建议新增：
- `gui/i18n/locales/cn.py`
- `gui/i18n/locales/en.py`

规则：
- [ ] 使用**扁平 dot key**，例如：
  - `shell.nav.dashboard`
  - `page.settings.title`
  - `dialog.takeover.title`
  - `event.task.complete`
  - `readiness.api_key.detail.missing`
- [ ] 参数化文案统一使用模板变量，如 `{duration}`、`{device_id}`
- [ ] 禁止在页面 / 服务层拼接自然语言句子

#### D. 历史事件数据结构（增量升级）
对**新生成事件**新增字段：
- [ ] `message_key`
- [ ] `message_params`
- [ ] `rendered_message`
- [ ] `lang`

兼容原则：
- [ ] 历史读取时，优先显示 `rendered_message`
- [ ] 若不存在，则回退到旧字段 `message`
- [ ] 不对旧记录做重译或批量迁移

#### E. 运行语言边界
- [ ] 保存设置后，GUI 通过 `I18nManager` 立即切换
- [ ] `ConfigService` 继续把 `OPEN_AUTOGLM_LANG` 写入 `.env`
- [ ] 当前已运行任务继续保持启动时语言
- [ ] 下次 `TaskService.start_task()` 时，仍通过 `build_command_args()` 带上新的 `--lang`

---

## Key Behavioral Rules
- [ ] 设置页是唯一正式语言切换入口；一期不加主窗口快捷切换
- [ ] `OPEN_AUTOGLM_LANG` 在设置页不再是自由文本输入，改为明确的语言下拉选择（简体中文 / English）
- [ ] GUI 静态文案、后续新弹窗、后续新事件应随切换立即更新
- [ ] 运行中的任务不被中断；其原始日志与任务内部输出保持原语种
- [ ] 工作台事件时间线显示的是**事件层翻译结果**，不是原始日志翻译结果
- [ ] 历史页旧记录保持原样；新记录保存新语种快照
- [ ] 缺词不静默回退到中文或英文，直接显示显式 key 占位并记录日志

---

## File Coverage Matrix

| Area | Must Cover | Critical Files |
|---|---|---|
| 主窗口壳层 | 窗口标题、导航、全局弹窗 | `gui/main_window.py` |
| 设置页 | 语言切换入口、字段标签、横幅、按钮 | `gui/pages/settings_page.py`, `gui/services/config_service.py` |
| 工作台 | 工具栏、状态条、环境摘要、结果摘要、事件列表 | `gui/pages/dashboard_page.py`, `gui/services/task_service.py`, `gui/services/readiness_service.py` |
| 历史页 | 筛选、标签页、状态、概览字段、事件显示 | `gui/pages/history_page.py`, `gui/services/history_service.py`, `gui/services/task_service.py` |
| 设备页 | 静态界面、连接/配对反馈、对话框 | `gui/pages/device_page.py`, `gui/services/device_service.py` |
| 诊断页 | 说明文案、结果项格式化、摘要栏 | `gui/pages/diagnostics_page.py`, `gui/services/readiness_service.py` |
| 通用弹窗/控件 | 共用对话框文案与标题 | `gui/widgets/themed_dialog.py`（如适用）, `gui/widgets/*` |
| 运行语言透传 | 配置 -> 命令行参数 -> main.py | `gui/services/config_service.py`, `main.py` |
| 词典与总线 | 统一翻译入口与页面广播 | `gui/i18n/manager.py`, `gui/i18n/page_adapter.py`, `gui/i18n/locales/*` |

---

## Phase Todo

### Phase 1 - 基础设施落地
- [x] 新建 `gui/i18n/manager.py`
- [x] 新建 `gui/i18n/page_adapter.py`
- [x] 新建 `gui/i18n/locales/cn.py`
- [x] 新建 `gui/i18n/locales/en.py`
- [x] 约定 key 命名规则与缺词占位格式（推荐：`[[key]]`）
- [x] 在 `MainWindow` 中注入 `I18nManager` 到 `services`
- [x] 参考 `ThemeManager` / `PageThemeAdapter` 完成页面注册与广播

**完成标准**
- [x] GUI 启动时能按 `OPEN_AUTOGLM_LANG` 解析当前语言
- [x] 手动触发语言变化后，注册页面能收到广播
- [x] 缺词时能稳定显示显式 key，而不是崩溃或静默回退

### Phase 2 - 设置页与主窗口壳层
- [x] 将 `SettingsPage` 中的 `OPEN_AUTOGLM_LANG` 从普通文本字段升级为明确的语言选择控件
- [x] 保存语言后立即调用 `I18nManager.set_language()`
- [x] 将 `MainWindow` 的窗口标题、导航按钮、底部版本辅助文案、全局弹窗接入翻译
- [x] 明确接管/卡住提示框的 key 与参数化规则

**完成标准**
- [x] 在设置页切换语言并保存后，导航与全局弹窗无需重启即可切换
- [x] `OPEN_AUTOGLM_LANG` 仍通过 `ConfigService` 正常持久化

### Phase 3 - 工作台与运行反馈
- [x] 将 `DashboardPage` 中以下区域 key 化：
  - [x] 工具栏按钮与 placeholder
  - [x] 状态条 key（状态 / 设备 / 镜像）
  - [x] 环境摘要条文本与 tooltip
  - [x] 结果摘要文本
  - [x] 镜像占位文案 / 接管横幅 / 恢复按钮
- [x] 将 `STATE_DISPLAY` / `MIRROR_STATE_DISPLAY` 改为通过 i18n 获取展示文本
- [x] 将 `readiness_service.py` 的 `label` / `detail` / `hint` 迁移为可翻译结构
- [x] 规定原始日志始终保持原文，事件时间线展示翻译后的事件层文案

**完成标准**
- [x] 工作台静态界面能完整切换语言
- [x] 重新检查环境后，摘要条与诊断摘要跟随当前语言
- [x] 运行中切换语言时，GUI 立即切换，但当前任务原始日志不变

### Phase 4 - TaskService 事件结构化
- [x] 改造 `TaskService._add_event()` 支持保存：`message_key / message_params / rendered_message / lang`
- [x] 将 `_infer_events_from_log()` 中可控的结构化事件改为 key 驱动
- [x] 保留旧 `message` 字段兼容读取
- [x] 对关键事件统一 key：
  - [x] `task_start`
  - [x] `process_started`
  - [x] `user_stop`
  - [x] `user_pause`
  - [x] `user_resume`
  - [x] `takeover_request`
  - [x] `task_complete`
  - [x] `task_failed`
  - [x] `cancelled`
  - [x] `stuck_detected`

**完成标准**
- [x] 新产生事件在工作台中以当前 GUI 语言显示
- [x] 事件序列化后具备新字段，供历史页直接消费
- [x] 原始 stdout/stderr 仍不参与翻译

### Phase 5 - 历史记录与历史页
- [x] `HistoryService.save_record()` 对新事件结构做安全序列化
- [x] `HistoryService._normalize_record()` 兼容旧记录与新记录共存
- [x] `HistoryPage` 改造以下文案：
  - [x] 页面标题
  - [x] 筛选器选项
  - [x] Tab 标题
  - [x] 状态标签
  - [x] 概览字段名
  - [x] 空状态 / 无日志提示
  - [x] 清空确认对话框
- [x] 历史事件显示优先使用 `rendered_message`，旧记录回退 `message`

**完成标准**
- [x] 切换语言后，旧历史记录不改变原语种
- [x] 切换语言后新运行的任务，其历史事件使用新语种保存
- [x] 历史页本身的壳层文案能即时切换

### Phase 6 - 设备页与诊断页收尾
- [x] 设备页静态文案、按钮、状态提示、配对对话框全部 key 化
- [x] 诊断页标题、说明文案、按钮、结果格式化、摘要栏全部 key 化
- [x] 统一处理 `ReadinessCheckResult` 的结果格式化，避免页面层继续拼中文句子

**完成标准**
- [x] 设备页和诊断页静态文案可完整切换
- [x] 诊断结果条目的 label/detail/hint 由当前语言驱动

### Phase 7 - 测试、扫描与补漏
- [x] 为 `I18nManager` 增加单元测试（建议新增 `tests/test_i18n_manager.py`）
- [x] 为历史兼容增加单元测试（建议新增 `tests/test_history_i18n_compat.py`）
- [x] 为 readiness 渲染与事件推断增加单元测试（新增 `tests/test_readiness_i18n.py`）
- [x] 为离屏 GUI 即时切换链路增加回归测试（新增 `tests/test_gui_i18n_headless.py`）
- [x] 对 `gui/` 范围做硬编码文案扫描，形成补漏清单
- [x] 继续清理首批漏项
- [x] 明确允许保留原文的例外项：日志原文、外部异常、第三方输出

**完成标准**
- [x] 有自动化测试覆盖 manager 与历史兼容
- [x] 有自动化测试覆盖 readiness 渲染与事件推断
- [x] 有自动化测试覆盖离屏 GUI 的即时切换与事件快照行为
- [x] 有一轮硬编码文案扫描结果用于补漏
- [x] 剩余未 i18n 项均被记录为明确 TODO，而非隐性遗漏

## Review Snapshot
- 已确认落地：i18n 总线、页面广播、`TaskService` 事件新字段、`HistoryService` 新旧事件兼容、`tests/test_i18n_manager.py`、`tests/test_history_i18n_compat.py`、`tests/test_readiness_i18n.py`、`tests/test_gui_i18n_headless.py`。
- 已修复关键阻塞 1：`I18nManager.__init__()` 现会同步 `_lang`；真实构造路径已由 `tests/test_i18n_manager.py` 覆盖，初始化语言状态与词典语言保持一致。
- 已修复关键阻塞 2：工作台当前会话事件时间线已优先显示 `rendered_message`；状态条、环境摘要、结果摘要、渠道下拉 tooltip 与镜像状态展示已接入当前语言重绘。
- 已修复关键阻塞 3：`readiness_service.py` 已改为结构化 key / params + render helpers；`DiagnosticsPage` 会在 `apply_i18n()` 时重绘已有结果与摘要。
- 本轮最终收口：`DashboardPage` 的渠道日志、镜像调试日志、tooltip / 下拉显示名与 `HistoryPage` 的状态标签回退已全部 key 化；`TaskService._infer_events_from_log()` 已改为 key 驱动并通过当前 GUI 语言生成接管理由。
- 自动化验证：`python -m pytest tests/test_theme_engine.py tests/test_history_i18n_compat.py tests/test_readiness_i18n.py tests/test_i18n_manager.py tests/test_gui_i18n_headless.py` 当前稳定为 71 项通过；其中离屏 GUI 回归覆盖 `MainWindow` 壳层、`DashboardPage`、`HistoryPage`、原始日志不重翻、旧历史快照不重渲，以及 `TaskService` 事件按生成时语言保存 `rendered_message / lang`。
- 最新扫描：`python scripts/scan_hardcoded_cn.py` 当前已报告“未发现明显硬编码残留”；首批 GUI i18n 漏项已全部清理完成。
- 复核结论：Phase 3 / Phase 4 / Phase 5 / Phase 7 已推进到“已完成”状态；依赖真实设备 / API 的手工链路验证仍可按 Verification Plan 执行，但当前实现与无人值守回归已满足一期交付要求。

---

## Acceptance Criteria
- [x] 在设置页把语言从简中切到英文并保存后，主窗口导航、页面标题、按钮、筛选器、状态标签、后续弹窗立即切到英文
- [x] 此时如果任务正在运行，GUI 壳层立即切换，但该任务的原始日志和其已启动进程内部输出保持原语种
- [x] 语言切换后再启动新任务，`ConfigService.build_command_args()` 传给 `main.py` 的 `--lang` 为新值
- [x] 工作台新增事件、诊断摘要、运行反馈横幅按当前语言显示
- [x] 历史页旧记录保持旧语种；新任务生成的新记录使用新语种
- [x] 若词典漏项，界面显示显式 key（例如 `[[event.task.complete]]`），同时记录缺词日志

---

## Risks and Pitfalls
- [ ] **服务层直接输出中文**：`task_service.py`、`readiness_service.py`、`device_service.py` 若继续直接返回自然语言，会造成界面“半中半英”
- [ ] **运行中切换误解**：如果不在规范中明确“当前任务不重启”，用户会误以为所有后续输出都应立即切语言
- [ ] **历史重渲污染**：如果历史页按当前语言重译旧记录，会破坏“旧不变”的约束
- [ ] **参数化文案散落**：若继续在 UI 或 service 中用 f-string 到处拼句子，后续维护成本会迅速升高
- [ ] **状态映射表遗漏**：`DashboardPage.STATE_DISPLAY`、`HistoryPage.STATE_LABEL`、诊断结果格式化等字典式展示最容易漏
- [ ] **缺词被静默吞掉**：如果默认回退中文/英文，会让漏项长期潜伏，违背本次明确要求

---

## Verification Plan

### A. 运行与手工验证
- [ ] 启动 GUI：`python gui_app.py`
- [ ] 进入设置页，将语言在“简体中文 / English”之间切换并保存
- [ ] 验证主窗口导航、工作台、历史页、诊断页、设备页壳层文案即时变化
- [ ] 在任务运行中切换语言，确认：
  - [ ] GUI 壳层立即变化
  - [ ] 当前任务不被中断
  - [ ] 当前任务原始日志保持原文
  - [ ] 新弹窗 / 新 GUI 摘要使用当前语言
- [ ] 切换语言后重新启动任务，确认新任务语种与 `OPEN_AUTOGLM_LANG` 一致

### B. 历史与序列化验证
- [ ] 运行一条中文任务，保存历史
- [ ] 切换到英文后运行第二条任务，再查看历史页
- [ ] 确认第一条旧历史仍保持中文，第二条新历史为英文
- [ ] 使用 Read 工具检查 `gui_history/index.json`，确认新事件包含新增字段：
  - [ ] `lang`
  - [ ] `message_key`
  - [ ] `message_params`
  - [ ] `rendered_message`

### C. 测试验证
- [x] 运行现有测试：`python -m pytest tests/test_theme_engine.py`
- [x] 运行新增 i18n 相关测试：`python -m pytest tests/test_readiness_i18n.py tests/test_i18n_manager.py`
- [x] 运行历史兼容测试：`python -m pytest tests/test_history_i18n_compat.py`
- [x] 运行离屏 GUI 回归测试：`python -m pytest tests/test_gui_i18n_headless.py`
- [x] 已等价执行当前全部测试文件（`tests/test_theme_engine.py` + `tests/test_history_i18n_compat.py` + `tests/test_readiness_i18n.py` + `tests/test_i18n_manager.py` + `tests/test_gui_i18n_headless.py`），当前稳定为 71 项通过

### D. 扫描补漏
- [x] 使用脚本对 `gui/` 内中文硬编码做首轮扫描，排除词典文件、原始日志常量与必要例外
- [x] 对扫描结果形成补漏清单；当前最新扫描已收敛为“未发现明显硬编码残留”
- [x] 验证缺词时显示显式 key，而不是沉默回退

---

## Critical Files to Modify

### Existing Files
- `gui/main_window.py`
- `gui/pages/dashboard_page.py`
- `gui/pages/settings_page.py`
- `gui/pages/device_page.py`
- `gui/pages/history_page.py`
- `gui/pages/diagnostics_page.py`
- `gui/services/config_service.py`
- `gui/services/task_service.py`
- `gui/services/history_service.py`
- `gui/services/readiness_service.py`
- `main.py`

### New Files (Recommended)
- `gui/i18n/manager.py`
- `gui/i18n/page_adapter.py`
- `gui/i18n/locales/cn.py`
- `gui/i18n/locales/en.py`
- `tests/test_i18n_manager.py`
- `tests/test_history_i18n_compat.py`
- `tests/test_readiness_i18n.py`
- `tests/test_gui_i18n_headless.py`

---

## Minimal Implementation Order
如果要按最稳妥顺序执行，建议严格按下面顺序推进：
1. `I18nManager` + `PageI18nAdapter`
2. `SettingsPage` 语言下拉 + `MainWindow` 全局广播
3. `DashboardPage` 静态文案 + `ReadinessService`
4. `TaskService` 事件结构化
5. `HistoryService` + `HistoryPage`
6. `DevicePage` + `DiagnosticsPage`
7. 单测、扫描补漏、验收

---

## Definition of Done
- [x] GUI 已具备稳定的简中 / 英文切换能力
- [x] 切换入口仅位于设置页，保存后即时全局生效
- [x] 当前任务不重启；后续新任务语言正确透传到 `main.py --lang`
- [x] 工作台运行反馈、历史事件、诊断摘要已纳入翻译体系
- [x] 原始日志不翻译，边界清晰
- [x] 旧历史不重渲，新历史按新语种保存
- [x] 缺词显式暴露 key，且有测试与扫描兜底
