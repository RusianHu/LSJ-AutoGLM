# HDC 实现总结

本文档总结了为 Open-AutoGLM 项目添加鸿蒙系统 HDC 支持的所有修改。

## 更新日期
2025-12-16

## 最新更新

### v1.2.0 - 鸿蒙应用列表支持

- ✅ 创建独立的鸿蒙应用配置文件 `apps_harmonyos.py`
- ✅ 内置 80+ 常用鸿蒙应用的 Bundle Name 映射
- ✅ 支持列出鸿蒙应用：`python main.py --device-type hdc --list-apps`
- ✅ 应用启动失败时提示可用应用列表
- ✅ 更新文档添加应用列表说明和查找方法

## 主要改进

### 1. 使用正确的 HDC 命令格式

根据鸿蒙系统的实际命令格式，更新了所有 UI 交互命令：

#### 点击操作
- **旧格式**: `hdc shell input tap X Y`
- **新格式**: `hdc shell uitest uiInput click X Y` ✅

#### 双击操作
- **旧格式**: 两次 `hdc shell input tap X Y`
- **新格式**: `hdc shell uitest uiInput doubleClick X Y` ✅

#### 长按操作
- **旧格式**: `hdc shell input swipe X Y X Y DURATION`
- **新格式**: `hdc shell uitest uiInput longClick X Y` ✅

#### 滑动操作
- **旧格式**: `hdc shell input swipe X1 Y1 X2 Y2 DURATION`
- **新格式**: `hdc shell uitest uiInput swipe X1 Y1 X2 Y2 DURATION` ✅

#### 返回键
- **旧格式**: `hdc shell input keyevent 2`
- **新格式**: `hdc shell uitest uiInput keyEvent Back` ✅

#### Home键
- **旧格式**: `hdc shell input keyevent 1`
- **新格式**: `hdc shell uitest uiInput keyEvent Home` ✅

### 2. 截屏命令兼容性

支持新旧两种鸿蒙版本的截屏命令（**注意：鸿蒙 HDC 只支持 JPEG 格式**）：

```bash
# 新版本（优先尝试）
hdc shell screenshot /data/local/tmp/tmp_screenshot.jpeg

# 旧版本（兜底方案）
hdc shell snapshot_display -f /data/local/tmp/tmp_screenshot.jpeg
```

**格式转换说明：**
- 设备上保存为 JPEG 格式（HDC 限制）
- 拉取到本地后自动转换为 PNG 格式
- 模型推理使用 PNG 格式的 base64 编码

### 3. 文本输入改进

鸿蒙的文本输入与 Android 不同，需要提供坐标：

```python
# 带坐标的输入（鸿蒙特有）
type_text("hello", x=100, y=100)  # hdc shell uitest uiInput inputText 100 100 hello

# 无坐标输入（需要先点击输入框）
tap(100, 100)  # 先点击输入框
type_text("hello")  # 然后输入文本
```

### 4. 命令输出显示

所有 HDC 命令都会自动显示在控制台：

```
[HDC] Running command: hdc shell uitest uiInput click 500 1000
[HDC] Running command: hdc shell screenshot /data/local/tmp/tmp.png
[HDC] Running command: hdc file recv /data/local/tmp/tmp.png /tmp/screenshot_abc.png
```

这有助于：
- 调试问题
- 学习 HDC 命令
- 发现命令执行失败的原因

## 修改的文件清单

### 核心实现文件

0. **phone_agent/config/apps_harmonyos.py** ⭐ 新增
   - 鸿蒙应用 Bundle Name 映射表
   - 支持 80+ 常用应用
   - 包括第三方应用、华为系统应用、华为服务
   - 提供 `get_harmonyos_app_package()` 和 `list_harmonyos_apps()` 函数

1. **phone_agent/hdc/connection.py**
   - 添加 `_run_hdc_command()` 函数用于命令输出
   - 添加 `set_hdc_verbose()` 控制输出开关
   - 所有 subprocess.run() 替换为 _run_hdc_command()

2. **phone_agent/hdc/device.py**
   - ✅ `tap()` - 使用 `uitest uiInput click`
   - ✅ `double_tap()` - 使用 `uitest uiInput doubleClick`
   - ✅ `long_press()` - 使用 `uitest uiInput longClick`
   - ✅ `swipe()` - 使用 `uitest uiInput swipe`
   - ✅ `back()` - 使用 `uitest uiInput keyEvent Back`
   - ✅ `home()` - 使用 `uitest uiInput keyEvent Home`
   - ✅ `launch_app()` - 使用鸿蒙应用列表，启动命令包含 `-a EntryAbility`
   - ✅ `get_current_app()` - 使用鸿蒙应用列表识别当前应用

3. **phone_agent/hdc/screenshot.py**
   - 支持 `screenshot` 和 `snapshot_display` 两种命令
   - 自动降级处理

4. **phone_agent/hdc/input.py**
   - 支持带坐标的文本输入
   - 改进清除文本方法（使用组合键）

5. **phone_agent/hdc/__init__.py**
   - 导出 `set_hdc_verbose` 函数

### 主程序文件

6. **main.py**
   - 使用 HDC 时自动启用 verbose 模式
   - 支持 `--list-apps` 列出鸿蒙应用
   - 根据设备类型显示不同的应用列表

### 文档文件

7. **HDC_USAGE.md**
   - 更新所有命令对照表
   - 添加 `uitest uiInput` 命令说明
   - 添加方向滑动、组合键等鸿蒙特有功能
   - 更新示例输出
   - 添加常见问题解答

8. **HDC_IMPLEMENTATION_SUMMARY.md**（本文件）
   - 实现总结文档

## 命令对照速查表

### 必须使用 uitest uiInput 的命令

| 操作 | 命令格式 |
|------|---------|
| 点击 | `hdc shell uitest uiInput click X Y` |
| 双击 | `hdc shell uitest uiInput doubleClick X Y` |
| 长按 | `hdc shell uitest uiInput longClick X Y` |
| 滑动 | `hdc shell uitest uiInput swipe X1 Y1 X2 Y2 DURATION` |
| 快速滑动 | `hdc shell uitest uiInput fling X1 Y1 X2 Y2 500` |
| 拖拽 | `hdc shell uitest uiInput drag X1 Y1 X2 Y2 500` |
| 返回键 | `hdc shell uitest uiInput keyEvent Back` |
| Home键 | `hdc shell uitest uiInput keyEvent Home` |
| 文本输入 | `hdc shell uitest uiInput inputText X Y text` |

### 方向滑动（鸿蒙特有）

| 方向 | 命令格式 | 参数说明 |
|------|---------|---------|
| 左滑 | `hdc shell uitest uiInput dircFling 0 500` | 0=左，500=速度 |
| 右滑 | `hdc shell uitest uiInput dircFling 1 600` | 1=右，600=速度 |
| 上滑 | `hdc shell uitest uiInput dircFling 2` | 2=上 |
| 下滑 | `hdc shell uitest uiInput dircFling 3` | 3=下 |

## 使用示例

### 查看支持的应用

```bash
# 列出所有支持的鸿蒙应用
python main.py --device-type hdc --list-apps
```

输出：
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
  - （80+ 应用）
```

### 基本使用

```bash
# 使用 HDC 控制鸿蒙设备（自动显示所有命令）
python main.py --device-type hdc --base-url http://localhost:8000/v1 --model "autoglm-phone-9b" "打开小红书"
```

### 你会看到的输出

```
[HDC] Running command: hdc list targets
[HDC] Running command: hdc shell screenshot /data/local/tmp/tmp_screenshot.png
[HDC] Running command: hdc file recv /data/local/tmp/tmp_screenshot.png /tmp/screenshot_xxx.png
[HDC] Running command: hdc shell uitest uiInput click 500 1000
[HDC] Running command: hdc shell aa start -b com.tencent.mm
```

### 手动测试命令

```bash
# 点击测试
hdc shell uitest uiInput click 500 1000

# 双击测试
hdc shell uitest uiInput doubleClick 500 1000

# 滑动测试
hdc shell uitest uiInput swipe 100 500 900 500 500

# 返回键
hdc shell uitest uiInput keyEvent Back
```

## 关键改进点

1. **命令格式完全正确** - 所有 UI 操作都使用 `uitest uiInput`
2. **自动命令显示** - 便于调试和学习
3. **兼容性处理** - 截屏等命令支持新旧版本
4. **详细文档** - 包含完整的命令对照和使用说明
5. **易于切换** - 通过 `--device-type` 参数在 ADB 和 HDC 之间切换
6. **独立应用列表** - 鸿蒙使用专用的应用配置，包含 80+ 常用应用
7. **智能提示** - 应用启动失败时显示可用应用列表

## 测试建议

1. **连接测试**
   ```bash
   hdc list targets
   python main.py --device-type hdc --list-devices
   ```

2. **截屏测试**
   ```bash
   hdc shell screenshot /data/local/tmp/test.jpeg
   hdc file recv /data/local/tmp/test.jpeg ~/test.jpeg
   ```

3. **点击测试**
   ```bash
   hdc shell uitest uiInput click 500 1000
   ```

4. **完整流程测试**
   ```bash
   python main.py --device-type hdc "打开设置"
   ```

## 支持的鸿蒙应用

系统内置 80+ 常用鸿蒙应用，包括：

### 第三方应用（13个）
百度、淘宝、WPS、快手、飞书、抖音、企业微信、同程旅行、唯品会、喜马拉雅、小红书等

### 华为系统应用（40+）
浏览器、计算器、日历、相机、时钟、云盘、邮件、文件管理器、录音机、笔记、相册、联系人、短信、电话、设置、健康、地图、钱包、智慧生活等

### 华为服务（10+）
应用市场、音乐、主题、天气、视频、阅读、游戏中心、搜索、我的华为等

### 添加新应用

如需添加新应用，编辑 `phone_agent/config/apps_harmonyos.py`：

```python
HARMONYOS_APP_PACKAGES = {
    "应用名": "com.example.bundle.name",
}
```

查找 Bundle Name：
```bash
hdc shell bm dump -a | grep "关键词"
```

## 注意事项

1. ⚠️ **文本输入**需要先点击输入框或提供坐标
2. ⚠️ **应用列表**鸿蒙使用独立的应用配置（`apps_harmonyos.py`）
3. ⚠️ **Bundle Name**与 Android 的 Package Name 不同
4. ⚠️ **设备权限**确保开启 USB 调试和相关权限
5. ✅ **命令输出**默认启用，方便调试
6. ✅ **降级处理**截屏等命令有兜底方案
7. ✅ **智能提示**应用未找到时会显示可用应用列表

## 参考资料

- [awesome-hdc](https://github.com/codematrixer/awesome-hdc) - HDC 命令参考
- [HarmonyOS 官方文档](https://developer.harmonyos.com/)
- [OpenHarmony 文档](https://gitee.com/openharmony/docs)

## 版本信息

- 实现版本：v1.2.0
- 支持的鸿蒙版本：HarmonyOS 2.0+
- 支持的 HDC 版本：2.0.0a+
- 支持的应用数量：80+ 常用应用

## 更新日志

### v1.2.0 (2025-12-16)
- ✅ 添加独立的鸿蒙应用配置文件
- ✅ 内置 80+ 常用应用的 Bundle Name
- ✅ 支持列出鸿蒙应用
- ✅ 应用启动失败时智能提示
- ✅ 更新文档添加应用查找方法

### v1.1.0 (2025-12-16)
- ✅ 修正所有 HDC 命令格式为 `uitest uiInput`
- ✅ 添加命令输出显示功能
- ✅ 支持截屏命令降级处理
- ✅ 完善文档和使用说明

### v1.0.0 (2025-12-16)
- ✅ 初始 HDC 支持实现
- ✅ 基础设备操作功能
- ✅ ADB/HDC 切换支持

---

**实现完成！现在可以完美支持鸿蒙设备，包含 80+ 常用应用，所有命令都使用正确的 uitest uiInput 格式。**
