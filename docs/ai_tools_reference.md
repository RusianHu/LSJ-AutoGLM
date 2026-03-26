# AI 工具与动作参考 / AI Tools & Action Reference

本文档汇总当前项目对 AI 模型暴露的动作（action）、参数格式、平台差异与常见调用示例。

适用范围：
- Android（ADB）
- HarmonyOS（HDC）
- iOS（WebDriverAgent / XCTest）

权威实现来源主要包括：
- `phone_agent/actions/handler.py`
- `phone_agent/actions/handler_ios.py`
- `phone_agent/adb/device.py`
- `phone_agent/hdc/device.py`
- `phone_agent/xctest/device.py`
- `phone_agent/config/prompts.py`
- `phone_agent/config/prompts_zh.py`
- `phone_agent/config/prompts_en.py`
- `phone_agent/config/prompts_thirdparty.py`

---

## 1. AI 输出协议 / Output Protocol

AI 每一步必须输出一个可解析的调用表达式，格式如下：

### 1.1 执行动作 / Execute an action

```python
 do(action="动作名", ...参数...)
```

### 1.2 结束任务 / Finish the task

```python
 finish(message="结束说明")
```

### 1.3 解析说明 / Parsing notes

项目使用安全解析器解析 AI 输出，支持：
- `do(...)`
- `finish(...)`
- `key=value` 参数形式
- 容错解析部分引号、换行、列表、字典内容

常见字符串参数键包括：
- `action`
- `app`
- `text`
- `message`
- `duration`

---

## 2. 坐标与参数约定 / Coordinate & Parameter Conventions

### 2.1 相对坐标 / Relative coordinates

AI 输出的坐标统一使用相对坐标，范围：
- 左上角：`[0, 0]`
- 右下角：`[999, 999]`

执行器会根据当前屏幕分辨率换算为绝对像素坐标。

### 2.2 敏感操作确认 / Sensitive action confirmation

对于可能涉及支付、隐私、删除等高风险点击，可为 `Tap` 增加：

```python
 do(action="Tap", element=[x, y], message="确认删除订单")
```

若宿主确认回调拒绝，本次动作会终止。

### 2.3 文本输入 / Text input

`Type` 与 `Type_Name` 都通过 `text` 参数传值：

```python
 do(action="Type", text="你好")
 do(action="Type_Name", text="张三")
```

### 2.4 等待 / Wait duration

`Wait` 使用字符串形式秒数：

```python
 do(action="Wait", duration="2 seconds")
```

若解析失败，执行器默认等待约 1 秒。

---

## 3. 当前支持的全部 AI 动作 / Full List of Supported AI Actions

下面列出当前执行器实际支持的动作。

| 动作名 | 主要参数 | 说明 | Android / HarmonyOS | iOS |
|---|---|---|---|---|
| `Find_App` | `query` | 查找 Android ADB 设备上的包名与启动 Activity | 仅 Android ADB | 不支持 |
| `Launch` | `app` | 启动应用 | 支持 | 支持 |
| `Tap` | `element`, 可选 `message` | 点击坐标 | 支持 | 支持 |
| `Type` | `text` | 输入文本 | 支持 | 支持 |
| `Type_Name` | `text` | 输入人名，执行上等同于 `Type` | 支持 | 支持 |
| `Swipe` | `start`, `end` | 滑动 | 支持 | 支持 |
| `Back` | 无 | 返回 | 支持 | 支持 |
| `Home` | 无 | 回到桌面 | 支持 | 支持 |
| `Double Tap` | `element` | 双击 | 支持 | 支持 |
| `Long Press` | `element` | 长按 | 支持 | 支持 |
| `Wait` | `duration` | 等待 | 支持 | 支持 |
| `Take_over` | `message` | 请求人工接管 | 支持 | 支持 |
| `Note` | `message` 可选 | 记录/占位动作 | 占位实现 | 占位实现 |
| `Call_API` | `instruction`（提示词层） | 总结/评论等占位动作 | 占位实现 | 占位实现 |
| `Interact` | 可选 `message` | 请求用户选择/交互 | 占位实现 | 占位实现 |
| `finish` | `message` | 结束任务 | 支持 | 支持 |

> 说明：
> - `Find_App` 当前仅在 Android ADB 执行器中可用，用于把“应用名/关键词”转换成后续 `Launch` 所需的包名。
> - `Note`、`Call_API`、`Interact` 当前在执行器中属于轻量/占位实现，主要用于规划链路兼容。
> - 真正的设备控制动作主要是 `Find_App`、`Launch`、`Tap`、`Type`、`Swipe`、`Back`、`Home`、`Double Tap`、`Long Press`、`Wait`。

---

## 4. 各动作详细参数 / Detailed Action Parameters

### 4.1 Find_App

#### 调用格式

```python
 do(action="Find_App", query="...")
```

#### 参数

- `query: str`
  - Android ADB：应用名片段、包名前缀、品牌词或任意关键词，例如 `settings`、`微信`、`com.tencent`

#### Android（ADB）规则

当前 `Find_App` 仅用于 Android ADB 设备：

1. 调用 [`search_installed_apps()`](phone_agent/device_factory.py:172) 搜索可启动 package/activity 条目
2. 成功时返回最多 10 条候选包名与 Activity
3. 结果消息会被回流到 [`PhoneAgent`](phone_agent/agent.py:56) 上下文中，供模型下一步直接调用 `Launch`
4. 若未找到、设备不是 ADB、或底层能力未实现，会返回明确失败信息

推荐示例：

```python
 do(action="Find_App", query="settings")
 do(action="Find_App", query="微信")
 do(action="Find_App", query="com.tencent")
```

#### 返回行为

- 成功：返回候选包名列表与推荐的下一步 `Launch` 调用
- 失败：返回错误信息，例如未找到匹配包名、未提供查询词、当前平台不支持

---

### 4.2 Launch

#### 调用格式

```python
 do(action="Launch", app="...")
```

#### 参数

- `app: str`
  - Android ADB：**优先传包名**，例如 `com.android.settings`
  - HarmonyOS HDC：通常传内置映射里的应用名，例如 `微信`
  - iOS：通常传内置映射里的应用名，例如 `设置`

#### Android（ADB）规则

当前 Android ADB 模式已改为 **package-only 优先**：

1. 若 `app` 看起来像 Android 包名，则直接按包名启动
2. 否则尝试内置静态映射
3. 不再默认做慢速“真实应用名 → 包名”动态解析

推荐示例：

```python
 do(action="Launch", app="com.android.settings")
 do(action="Launch", app="com.tencent.mm")
```

不推荐但仍可能命中内置映射的写法：

```python
 do(action="Launch", app="微信")
```

#### 返回行为

- 成功：继续任务
- 失败：返回错误信息，例如未找到应用或包名无效

---

### 4.3 Tap

#### 调用格式

```python
 do(action="Tap", element=[x, y])
```

或敏感点击：

```python
 do(action="Tap", element=[x, y], message="确认执行敏感操作")
```

#### 参数

- `element: list[int, int]`
  - 相对坐标，范围 0-999
- `message: str`（可选）
  - 若存在，将触发宿主确认机制

---

### 4.4 Type / Type_Name

#### 调用格式

```python
 do(action="Type", text="搜索内容")
 do(action="Type_Name", text="张三")
```

#### 参数

- `text: str`

#### Android 行为

- 自动切换到 ADB Keyboard
- 清空现有文本
- 输入新文本
- 恢复原输入法

#### iOS 行为

- 清空现有文本
- 输入文本
- 尝试隐藏键盘

---

### 4.5 Swipe

#### 调用格式

```python
 do(action="Swipe", start=[x1, y1], end=[x2, y2])
```

#### 参数

- `start: list[int, int]`
- `end: list[int, int]`

---

### 4.6 Back

#### 调用格式

```python
 do(action="Back")
```

#### 行为差异

- Android / HarmonyOS：返回键事件
- iOS：返回手势/返回逻辑

---

### 4.7 Home

#### 调用格式

```python
 do(action="Home")
```

#### 行为差异

- Android / HarmonyOS：Home 键事件
- iOS：回到主屏幕

---

### 4.8 Double Tap

#### 调用格式

```python
 do(action="Double Tap", element=[x, y])
```

#### 参数

- `element: list[int, int]`

---

### 4.9 Long Press

#### 调用格式

```python
 do(action="Long Press", element=[x, y])
```

#### 参数

- `element: list[int, int]`

---

### 4.10 Wait

#### 调用格式

```python
 do(action="Wait", duration="2 seconds")
```

#### 参数

- `duration: str`

#### 说明

执行器会尽量把字符串解析为秒数。

---

### 4.11 Take_over

#### 调用格式

```python
 do(action="Take_over", message="请手动完成登录后继续")
```

#### 参数

- `message: str`

#### 用途

- 登录
- 验证码
- 付款确认
- 任何必须人工完成的步骤

---

### 4.12 Note

#### 调用格式

```python
 do(action="Note", message="True")
```

#### 用途

用于兼容提示词里的“记录当前页面内容”语义。
当前执行器为占位实现，不直接对设备产生控制动作。

---

### 4.13 Call_API

#### 调用格式

```python
 do(action="Call_API", instruction="总结当前页面")
```

#### 参数

- 常见提示词写法使用 `instruction`

#### 用途

用于兼容提示词里的“总结/评论页面内容”语义。
当前执行器为占位实现。

---

### 4.14 Interact

#### 调用格式

```python
 do(action="Interact")
```

#### 用途

当存在多个候选项，需要宿主或用户介入选择时使用。
当前执行器返回 `User interaction required` 一类提示。

---

### 4.15 finish

#### 调用格式

```python
 finish(message="任务完成")
```

#### 参数

- `message: str`

#### 用途

表示当前任务已经完整结束。

---

## 5. 平台差异 / Platform Differences

### 5.1 Android（ADB）

- 查找应用包名：优先使用 `do(action="Find_App", query="...")`
- 启动应用：推荐直接传**包名**
- 输入：依赖 ADB Keyboard
- 点击/滑动/返回/Home：通过 ADB 执行
- 仍可配合 CLI 辅助命令进行离线排查：
  - `python main.py --device-type adb --list-device-apps`
  - `python main.py --device-type adb --find-app settings`

### 5.2 HarmonyOS（HDC）

- 启动应用主要依赖内置 `APP_PACKAGES` / `APP_ABILITIES`
- 常见写法仍是传应用名，而不是 bundle 名
- 启动底层通过 `aa start -b <bundle> -a <ability>`

### 5.3 iOS（WebDriverAgent）

- 启动应用依赖内置 bundle ID 映射
- 调用链基于 WebDriverAgent/XCTest
- 点击、输入、返回、Home、滑动都有独立 iOS 实现

---

## 6. 常见 AI 调用示例 / Common AI Invocation Examples

### 6.1 Android：打开设置

```python
 do(action="Launch", app="com.android.settings")
```

### 6.2 Android：点击右上角按钮

```python
 do(action="Tap", element=[920, 80])
```

### 6.3 Android：搜索微信

```python
 do(action="Type", text="微信")
```

### 6.4 Android：下滑列表

```python
 do(action="Swipe", start=[500, 800], end=[500, 250])
```

### 6.5 请求用户登录

```python
 do(action="Take_over", message="请先手动登录并返回应用")
```

### 6.6 完成任务

```python
 finish(message="已完成设置检查")
```

---

## 7. 与 AI 调用最相关的 CLI 辅助工具 / CLI Helpers Related to AI Invocation

这些命令不是 AI 动作本身，而是当前项目提供的 **CLI 辅助工具**，适合在调试、排查或人工预览时使用。

也就是说：
- AI 在运行时直接调用的是 `do(...)` 动作协议
- Android ADB 模式下，获取包名现在优先通过 `do(action="Find_App", query="...")` 完成
- CLI 仍然适合人工快速查看 package/activity 列表，或在提示词调试时准备参数
- 一旦拿到包名，AI 就可以直接把包名传给 `Launch`

### 7.1 列出设备上的可启动包

```powershell
 python main.py --device-type adb --list-device-apps
```

输出内容为：
- package name
- launcher activity

### 7.2 搜索包或 Activity

```powershell
 python main.py --device-type adb --find-app settings
 python main.py --device-type adb --find-app wechat
 python main.py --device-type adb --find-app com.tencent
```

### 7.3 列出已连接设备

```powershell
 python main.py --list-devices
```

---

## 8. 推荐实践 / Recommended Best Practices

### 8.1 Android ADB

优先写：

```python
 do(action="Launch", app="com.android.settings")
```

避免写：

```python
 do(action="Launch", app="设置")
```

除非这个名称已经存在于内置映射中，并且你明确依赖静态映射。

### 8.2 坐标动作

- 只输出一个动作
- 所有坐标都用相对坐标
- 优先先 `Launch` 再 `Tap`
- 加载慢时优先 `Wait`

### 8.3 结束条件

当任务已完成，不要继续多做一步；直接：

```python
 finish(message="任务完成")
```

---

## 9. 当前限制 / Current Limitations

- `Note`、`Call_API`、`Interact` 目前为兼容性占位实现，不是完整的业务执行器
- Android ADB 已不再默认做“真实名称 → 包名”的慢速全量解析，而是通过 `Find_App` + `Launch` 两步完成
- HarmonyOS 与 iOS 的 `Launch` 仍主要依赖内置映射，而不是动态包扫描
- `Find_App` 当前仅支持 Android ADB，不支持 HarmonyOS / iOS
- 第三方模型若跳过 `Find_App` 且直接输出模糊应用名，在 Android ADB 下仍可能导致 `Launch` 失败

---

## 10. 快速结论 / Quick Summary

如果你要给 AI 写动作：

- Android ADB：未知包名时先用 `Find_App`，启动时 `Launch` 优先传**包名**
- CLI 仍可用于人工排查 package/activity 列表
- 坐标统一 `0-999`
- 所有动作统一用 `do(...)`
- 完成统一用 `finish(...)`
- Android 查包名推荐先用：

```python
 do(action="Find_App", query="settings")
```

---

## 11. 相关文档 / Related Documents

- `README.md`
- `README_en.md`
- `README_official.md`
- `AGENTS.md`
- `phone_agent/config/prompts.py`
- `phone_agent/config/prompts_zh.py`
- `phone_agent/config/prompts_en.py`
- `phone_agent/config/prompts_thirdparty.py`
