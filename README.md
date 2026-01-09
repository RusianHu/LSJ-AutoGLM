# Open-AutoGLM (老司机启动器)

这是 Open-AutoGLM 的老司机启动器版本，包含针对本地开发环境的特殊更改和优化。

## 官方文档链接

原项目的详细说明文档已被重命名，请查阅以下链接获取完整的使用指南和项目介绍：

- **[官方说明文档 (Original README)](README_official.md)**
- [English README](README_en.md)
- [Agent 规则说明 (AGENTS.md)](AGENTS.md)

---

## 定制化更改说明

本版本在原版基础上进行了以下修改，以适配特定的开发流程和硬件环境：

### 1. 交互式启动器 (`launcher.py`)

交互式启动器，提供 TUI 界面：

<details>
<summary>点击展开 TUI 界面预览</summary>

```
============================================================
  🤖 Open-AutoGLM 交互式启动器
  📱 AI 驱动的手机自动化控制系统
============================================================

──────────────────── 系统状态 ────────────────────
  ✅ ADB: Android Debug Bridge version 35.0.2
  ✅ 已连接设备: 1 台
     📱 77eaf689 [USB] (xiaomi) ✓键盘

──────────────────── API 配置 ────────────────────
  🌐 API地址: https://api-inference.modelscope.cn/v1
  🤖 模型: ZhipuAI/AutoGLM-Phone-9B
  🔑 API Key: sk-xxxx...xxxx

──────────────────── 当前设置 ────────────────────
  🎯 目标设备: 77eaf689
  🌍 语言: 中文
  📊 最大步数: 100

──────────────────── 主菜单 ────────────────────
  [1] 🚀 启动 Phone Agent (交互模式)
  [2] 📝 执行单个任务
  [3] 📱 设备管理
  [4] 🔧 选择模型/API
  [5] ⚙️  配置设置
  [6] 🔍 系统检查
  [7] 📖 使用帮助
  [0] 🚪 退出
────────────────────────────────────────────────────────────
```

</details>

#### 核心功能
- **设备管理**: USB/无线连接、设备切换、ADB Keyboard 安装
- **API 预设**: 快捷切换 ModelScope、智谱、第三方中转站、本地服务
- **系统检查**: 一键检测 ADB、设备、API、Python 依赖状态
- **任务执行**: 交互模式 / 单任务模式

#### 自动加载 API 预设
- 启动时自动读取环境变量 `OPEN_AUTOGLM_DEFAULT_PRESET`
- 支持预设: `modelscope`, `zhipu`, `newapi`, `local_openai`
- 自动应用对应的 `Base URL`、`Model` 以及 `API Key` 配置

#### 本地 OpenAI 兼容服务支持
- 支持连接本地部署的 OpenAI 兼容服务（如 LMStudio、Ollama、vLLM 等）
- 可配置允许空 API Key（部分本地服务不需要认证）
- 自动规范化 Base URL（自动补全 `/v1` 路径）

#### 安全特性
- 敏感信息（API Key）从 `.env` 文件读取，避免硬编码
- 默认不在配置文件中持久化 API Key（可通过环境变量开启）
- 控制台显示 API Key 时自动遮蔽

### 2. 环境变量配置 (`.env.example`)

完整的环境变量配置模板，支持：

```properties
# 默认启动预设 (自动覆盖 BASE_URL 和 MODEL)
OPEN_AUTOGLM_DEFAULT_PRESET=modelscope

# 各预设的 API Key（从环境变量注入，不写入代码）
OPEN_AUTOGLM_MODELSCOPE_API_KEY=sk-xxx
OPEN_AUTOGLM_ZHIPU_API_KEY=xxx.xxx
OPEN_AUTOGLM_NEWAPI_API_KEY=sk-xxx

# 第三方模型提示词工程
OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT=true
OPEN_AUTOGLM_THIRDPARTY_THINKING=true

# 本地 OpenAI 兼容服务
OPEN_AUTOGLM_LOCAL_OPENAI_BASE_URL=http://127.0.0.1:1234
OPEN_AUTOGLM_LOCAL_OPENAI_ALLOW_EMPTY_KEY=true
```

### 3. 项目配置文档 (`AGENTS.md`)

为 AI Coding Agent（如 Claude Code、Kilo Code）设计的项目规则文件：

- **GitHub 仓库信息**: Fork/上游地址、同步命令
- **设备配置**: 小米 14 Ultra 的 USB ID、无线调试端口
- **API 配置表**: ModelScope、智谱、第三方中转站的完整参数
- **快速启动命令**: 各种场景的启动示例
- **注意事项**: 第三方模型使用 `--thirdparty` 参数的重要说明

### 4. 第三方模型支持 (`--thirdparty`)

针对非 AutoGLM 原生模型（如 Qwen3-VL）的适配：

- **`--thirdparty`**: 启用第三方模型提示词工程
- **`--thirdparty-thinking`**: 启用思考输出（`<think>`/`<answer>` 格式）
- **`--thirdparty-no-thinking`**: 禁用思考（纯动作输出，更兼容部分中转站）
- **`--no-compress-image`**: 禁用截图压缩（保持原图质量）

## 快速使用

### 从 GitHub 部署

```powershell
# 克隆仓库（老司机启动器版本）
git clone https://github.com/RusianHu/LSJ-AutoGLM.git
cd LSJ-AutoGLM

# 或克隆官方上游仓库
git clone https://github.com/zai-org/Open-AutoGLM.git
cd Open-AutoGLM

# 安装依赖
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key
```

### 方式一：使用启动器（推荐）

1. **配置环境**: 复制 `.env.example` 为 `.env`，填入 API Key
2. **设置预设**: 在 `.env` 中设置 `OPEN_AUTOGLM_DEFAULT_PRESET`（如 `modelscope`）
3. **启动**:

```powershell
python launcher.py
```

启动器将自动识别预设，显示系统状态并进入主菜单。

### 方式二：直接运行 main.py

```powershell
# 使用 ModelScope
python main.py --base-url "https://api-inference.modelscope.cn/v1" --model "ZhipuAI/AutoGLM-Phone-9B" --apikey "你的Key" "打开微信"

# 使用第三方模型（如 Qwen3-VL）
python main.py --thirdparty --base-url "https://your-api.com/v1" --model "Qwen/Qwen3-VL-235B" --apikey "你的Key" "打开设置"
```

---

## 许可证

本项目基于 [Apache License 2.0](LICENSE) 开源许可证。
