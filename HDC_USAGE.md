# HDC 鸿蒙系统支持使用说明

本项目已添加对 HarmonyOS（鸿蒙系统）的支持，通过 HDC（HarmonyOS Device Connector）工具进行设备控制。

## 功能特性

- ✅ 完整的 HDC 命令支持
- ✅ 自动显示所有执行的 HDC 命令（便于调试）
- ✅ 支持 USB 和远程连接
- ✅ 与 ADB 相同的操作接口
- ✅ 通过 `--device-type` 参数快速切换

## 安装 HDC

### 1. 下载 HDC 工具

从以下来源获取 HDC：
- HarmonyOS SDK
- OpenHarmony 官方仓库：https://gitee.com/openharmony/docs

### 2. 配置环境变量

将 HDC 可执行文件路径添加到系统 PATH：

**macOS/Linux:**
```bash
export PATH=$PATH:/path/to/hdc
```

**Windows:**
在系统环境变量中添加 HDC 所在目录到 PATH。

### 3. 验证安装

```bash
hdc -v
```

应该输出 HDC 版本信息。

## 使用方法

### 基本使用

#### 使用 HDC 控制鸿蒙设备

```bash
python main.py --device-type hdc --base-url http://localhost:8000/v1 --model "autoglm-phone-9b" "打开微信"
```

#### 查看 HDC 命令输出

使用 HDC 时，所有命令都会自动显示，格式如下：

```
[HDC] Running command: hdc list targets
[HDC] Running command: hdc shell snapshot_display -f /data/local/tmp/tmp.png
[HDC] Running command: hdc file recv /data/local/tmp/tmp.png /tmp/screenshot_xxx.png
[HDC] Running command: hdc shell input tap 500 1000
```

#### 使用环境变量

```bash
# 设置默认使用 HDC
export PHONE_AGENT_DEVICE_TYPE=hdc

# 控制 HDC 命令输出（默认已启用）
export HDC_VERBOSE=true

# 运行
python main.py "打开美团搜索附近的火锅店"
```

### 设备管理

#### 列出连接的鸿蒙设备

```bash
python main.py --device-type hdc --list-devices
```

#### 连接远程鸿蒙设备

```bash
# 通过 WiFi 连接
python main.py --device-type hdc --connect 192.168.1.100:5555

# 连接后执行任务
python main.py --device-type hdc --device-id 192.168.1.100:5555 "打开淘宝"
```

#### 启用 TCP/IP 模式

```bash
# 首先通过 USB 连接设备，然后启用 TCP/IP
python main.py --device-type hdc --enable-tcpip 5555
```

### 列出支持的鸿蒙应用

```bash
python main.py --device-type hdc --list-apps
```

输出示例：
```
Supported HarmonyOS apps:
  - WPS
  - 阿里巴巴
  - 百度
  - 抖音
  - 淘宝
  - 小红书
  - 浏览器
  - 相机
  - 设置
  - ...（更多应用）
```

### 交互模式

```bash
python main.py --device-type hdc --base-url http://localhost:8000/v1
```

然后输入任务：
```
Enter your task: 打开小红书搜索美食
Enter your task: 打开抖音刷视频
Enter your task: quit
```

## HDC 与 ADB 命令对照

### 基础命令对照

| 功能 | ADB 命令 | HDC 命令 |
|------|----------|----------|
| 列出设备 | `adb devices` | `hdc list targets` |
| 连接远程设备 | `adb connect IP:PORT` | `hdc tconn IP:PORT` |
| 断开设备 | `adb disconnect` | `hdc tdisconn` |
| 启动应用 | `adb shell monkey -p PACKAGE` | `hdc shell aa start -b BUNDLE` |
| 文件拉取 | `adb pull` | `hdc file recv` |
| 文件推送 | `adb push` | `hdc file send` |

### UI 交互命令对照（重要）

鸿蒙系统使用 `uitest uiInput` 进行 UI 交互，与 Android 的 `input` 命令有很大不同：

| 功能 | ADB 命令 | HDC 命令 |
|------|----------|----------|
| 截屏 | `adb shell screencap -p` | `hdc shell screenshot /path/to/screenshot.jpeg` (仅支持JPEG) |
| 点击 | `adb shell input tap X Y` | `hdc shell uitest uiInput click X Y` |
| 双击 | `adb shell input tap X Y`（执行两次） | `hdc shell uitest uiInput doubleClick X Y` |
| 长按 | `adb shell input swipe X Y X Y 1000` | `hdc shell uitest uiInput longClick X Y` |
| 滑动 | `adb shell input swipe X1 Y1 X2 Y2 DURATION` | `hdc shell uitest uiInput swipe X1 Y1 X2 Y2 DURATION` |
| 快速滑动 | - | `hdc shell uitest uiInput fling X1 Y1 X2 Y2 500` |
| 拖拽 | - | `hdc shell uitest uiInput drag X1 Y1 X2 Y2 500` |
| 返回键 | `adb shell input keyevent 4` | `hdc shell uitest uiInput keyEvent Back` |
| Home键 | `adb shell input keyevent KEYCODE_HOME` | `hdc shell uitest uiInput keyEvent Home` |
| 输入文本 | `adb shell input text "hello"` | `hdc shell uitest uiInput inputText X Y hello` |

### 方向滑动命令（鸿蒙特有）

```bash
# 左滑
hdc shell uitest uiInput dircFling 0 500

# 右滑
hdc shell uitest uiInput dircFling 1 600

# 上滑
hdc shell uitest uiInput dircFling 2

# 下滑
hdc shell uitest uiInput dircFling 3
```

### 组合键（鸿蒙特有）

```bash
# 组合键粘贴操作
hdc shell uitest uiInput keyEvent 2072 2038
```

## 命令输出示例

当使用 HDC 时，你会看到类似以下的输出：

```bash
$ python main.py --device-type hdc "打开微信并点击某个按钮"

🔍 Checking system requirements...
--------------------------------------------------
1. Checking HDC installation... ✅ OK (Ver: 2.0.0a)
2. Checking connected devices... ✅ OK (1 device(s): FMR0223C13000649)
3. Skipping keyboard check for HarmonyOS... ✅ OK (using native input)
--------------------------------------------------
✅ All system checks passed!

==================================================
Phone Agent - AI-powered phone automation
==================================================
Model: autoglm-phone-9b
Base URL: http://localhost:8000/v1
Max Steps: 100
Language: cn
Device Type: HDC
Device: FMR0223C13000649 (auto-detected)
==================================================

Task: 打开微信并点击某个按钮

[HDC] Running command: hdc shell screenshot /data/local/tmp/tmp_screenshot.png
[HDC] Running command: hdc file recv /data/local/tmp/tmp_screenshot.png /tmp/screenshot_abc123.png
[HDC] Running command: hdc shell hidumper -s WindowManagerService -a -a

==================================================
💭 思考过程:
--------------------------------------------------
需要启动微信应用
--------------------------------------------------
🎯 执行动作:
{
  "_metadata": "do",
  "action": "Launch",
  "app": "微信"
}
==================================================

[HDC] Running command: hdc shell aa start -b com.tencent.mm
[HDC] Running command: hdc shell screenshot /data/local/tmp/tmp_screenshot.png
[HDC] Running command: hdc file recv /data/local/tmp/tmp_screenshot.png /tmp/screenshot_def456.png

==================================================
💭 思考过程:
--------------------------------------------------
识别到按钮在坐标 (500, 1000)，需要点击
--------------------------------------------------
🎯 执行动作:
{
  "_metadata": "do",
  "action": "Tap",
  "element": [500, 1000]
}
==================================================

[HDC] Running command: hdc shell uitest uiInput click 540 2400

🎉 ================================================
✅ 任务完成: 已成功完成任务
==================================================
```

## 调试技巧

### 1. 查看详细的 HDC 命令

HDC 模式下默认启用命令输出。如果需要关闭：

```python
from phone_agent.hdc import set_hdc_verbose
set_hdc_verbose(False)
```

或通过环境变量：
```bash
export HDC_VERBOSE=false
python main.py --device-type hdc "你的任务"
```

### 2. 检查设备连接

```bash
# 直接使用 HDC 命令检查
hdc list targets

# 通过程序检查
python main.py --device-type hdc --list-devices
```

### 3. 测试单个命令

```bash
# 截图测试（注意：必须使用 .jpeg 扩展名）
hdc shell screenshot /data/local/tmp/test.jpeg
hdc file recv /data/local/tmp/test.jpeg ~/test.jpeg

# 点击测试（使用 uitest）
hdc shell uitest uiInput click 500 1000

# 双击测试
hdc shell uitest uiInput doubleClick 500 1000

# 长按测试
hdc shell uitest uiInput longClick 500 1000

# 滑动测试
hdc shell uitest uiInput swipe 100 500 900 500 500

# 返回键
hdc shell uitest uiInput keyEvent Back

# Home键
hdc shell uitest uiInput keyEvent Home

# 启动应用测试
hdc shell aa start -b com.example.app
```

## 支持的鸿蒙应用

系统已内置常用鸿蒙应用的 Bundle Name 映射，包括：

### 第三方应用
- 百度、淘宝、WPS、快手、飞书、抖音、企业微信
- 同程旅行、唯品会、喜马拉雅、小红书

### 华为系统应用
- 工具类：浏览器、计算器、日历、相机、时钟、云盘、邮件、文件管理器、录音机、笔记
- 媒体类：相册、图库
- 通讯类：联系人、短信、电话
- 设置类：设置
- 生活服务：健康、地图、钱包、智慧生活、小艺

### 华为服务
- 应用市场、音乐、主题、天气、视频、阅读、游戏中心、搜索、我的华为

查看完整列表：
```bash
python main.py --device-type hdc --list-apps
```

### 添加新应用

如果你需要的应用不在列表中，可以手动添加到 `phone_agent/config/apps_harmonyos.py`：

```python
HARMONYOS_APP_PACKAGES = {
    # ...
    "你的应用名": "com.example.bundle.name",
}
```

或者在运行时查找应用的 Bundle Name：
```bash
# 列出设备上所有已安装的应用
hdc shell bm dump -a

# 查找特定应用的包名
hdc shell bm dump -a | grep "应用关键词"
```

## 注意事项

1. **UI 交互命令差异**：
   - 鸿蒙使用 `uitest uiInput` 系列命令，与 Android 的 `input` 命令完全不同
   - 所有点击、滑动等操作都通过 `uitest uiInput` 执行
   - 文本输入在鸿蒙上需要提供坐标：`inputText X Y text`

2. **应用包名差异**：
   - 鸿蒙应用使用 Bundle Name 而非 Android 的 Package Name
   - 已内置常用应用的 Bundle Name 映射
   - 启动应用时使用 `-a EntryAbility` 指定主入口

3. **输入法支持**：
   - 鸿蒙系统使用原生输入法，不需要安装 ADB Keyboard
   - 文本输入通过 `uitest uiInput inputText` 命令，需要先点击输入框获得焦点
   - 或者直接提供输入框坐标进行输入

4. **权限设置**：
   - 确保鸿蒙设备已开启 USB 调试
   - 某些操作可能需要额外的安全设置权限
   - 部分设备可能需要开启"允许模拟位置"等选项

5. **命令输出**：所有 HDC 命令都会显示在控制台，这有助于：
   - 调试问题
   - 了解系统如何与设备交互
   - 学习 HDC 命令的使用
   - 发现命令执行失败的原因

6. **截屏命令兼容性**：
   - ⚠️ **重要**：鸿蒙 HDC 只支持 JPEG 格式，不支持 PNG
   - 新版本鸿蒙：`hdc shell screenshot /data/local/tmp/screenshot.jpeg`
   - 旧版本鸿蒙：`hdc shell snapshot_display -f /data/local/tmp/screenshot.jpeg`
   - 系统会自动尝试两种方法，并将 JPEG 转换为 PNG 供模型使用

## 常见问题

### Q: HDC 命令输出太多，如何关闭？

A: 设置环境变量 `HDC_VERBOSE=false` 或在代码中调用 `set_hdc_verbose(False)`。

### Q: 如何在 Android 和鸿蒙设备之间切换？

A: 使用 `--device-type` 参数：
- Android: `--device-type adb`（默认）
- 鸿蒙: `--device-type hdc`

### Q: 能否同时连接 Android 和鸿蒙设备？

A: 同一时间只能使用一种设备类型。如需切换，重新运行程序并指定不同的 `--device-type`。

### Q: HDC 与 ADB 的功能有什么区别？

A: 核心功能相同，但有重要差异：
- **UI 交互命令完全不同**：HDC 使用 `uitest uiInput` 而不是 `input`
- 应用管理方式不同（Bundle vs Package）
- 某些系统服务名称不同
- 文本输入方式不同（HDC 需要坐标）

### Q: 为什么文本输入不工作？

A: 鸿蒙的文本输入与 Android 不同：
1. 方式一：先用 `click` 点击输入框，然后系统会尝试使用 `input text` 命令
2. 方式二：直接使用 `uitest uiInput inputText X Y text`，需要知道输入框坐标
3. 推荐先点击输入框获得焦点，然后输入文本

### Q: 我的命令执行失败了怎么办？

A: 查看控制台输出的 HDC 命令：
1. 检查命令格式是否正确（特别注意 `uitest uiInput` 格式）
2. 手动在终端执行相同命令测试
3. 检查设备权限设置
4. 确认鸿蒙版本是否支持该命令

### Q: 如何找到应用的 Bundle Name？

A: 使用以下方法：
1. 列出所有应用：`hdc shell bm dump -a`
2. 搜索特定应用：`hdc shell bm dump -a | grep "关键词"`
3. 查看应用详情：`hdc shell bm dump -n <bundle_name>`
4. 将找到的 Bundle Name 添加到 `apps_harmonyos.py` 配置文件

### Q: 为什么应用启动失败？

A: 可能的原因：
1. Bundle Name 不正确 - 检查应用是否在 `apps_harmonyos.py` 中
2. Ability 名称不对 - 大部分应用使用 "EntryAbility"，少数可能不同
3. 应用未安装 - 确认设备上已安装该应用
4. 权限问题 - 某些应用可能需要额外权限

## 技术支持

如遇到问题，请提供以下信息：

1. HDC 版本：`hdc -v`
2. 设备信息：`hdc list targets`
3. 错误日志（包含命令输出）
4. 鸿蒙系统版本

提交 Issue：https://github.com/zai-org/Open-AutoGLM/issues
