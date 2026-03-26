# Open-AutoGLM (LSJ Launcher)

[Chinese](./README.md)

This is the LSJ Launcher version of Open-AutoGLM, containing special changes and optimizations for local development environments.

## Official Documentation

The original project's detailed documentation has been renamed. Please refer to the following links for the complete usage guide and project introduction:

- **[Official Documentation (Original README)](README_official.md)**
- [Chinese README](README.md)
- [AI Tools & Action Reference](docs/ai_tools_reference.md)

---

## Customization Notes

Regular users can check [GitHub Releases](https://github.com/RusianHu/LSJ-AutoGLM/releases) for the packaged version to install and run directly.

CLI version adapted for specific development workflows and hardware environments:

### 1. Interactive Launcher (`launcher.py`)

An interactive launcher with a TUI interface:

<details>
<summary>Click to expand TUI preview</summary>

```
============================================================
  Open-AutoGLM Interactive Launcher
  AI-Powered Phone Automation Control System
============================================================

---- System Status ----
  [OK] ADB: Android Debug Bridge version 35.0.2
  [OK] Connected Devices: 1
       77eaf689 [USB] (xiaomi) Keyboard OK

---- API Configuration ----
  API URL: https://api-inference.modelscope.cn/v1
  Model: ZhipuAI/AutoGLM-Phone-9B
  API Key: sk-xxxx...xxxx

---- Current Settings ----
  Target Device: 77eaf689
  Language: Chinese
  Max Steps: 100

---- Main Menu ----
  [1] Launch Phone Agent (Interactive Mode)
  [2] Execute Single Task
  [3] Device Management
  [4] Select Model/API
  [5] Configuration Settings
  [6] System Check
  [7] Usage Help
  [0] Exit
------------------------------------------------------------
```

</details>

#### Core Features
- **Device Management**: USB/wireless connection, device switching, ADB Keyboard installation
- **API Presets**: Quick switching between ModelScope, Zhipu, third-party relay, and local services
- **System Check**: One-click detection of ADB, device, API, and Python dependency status
- **Task Execution**: Interactive mode / single task mode

#### Auto-Load API Presets
- Automatically reads the `OPEN_AUTOGLM_DEFAULT_PRESET` environment variable on startup
- Supported presets: `modelscope`, `zhipu`, `newapi`, `local_openai`
- Automatically applies the corresponding `Base URL`, `Model`, and `API Key` configuration

#### Local OpenAI-Compatible Service Support
- Supports connecting to locally deployed OpenAI-compatible services (e.g., LMStudio, Ollama, vLLM)
- Configurable to allow empty API Key (some local services do not require authentication)
- Automatically normalizes Base URL (auto-appends `/v1` path)

#### Security Features
- Sensitive information (API Key) is read from the `.env` file to avoid hardcoding
- API Key is not persisted in config files by default (can be enabled via environment variable)
- API Key is automatically masked when displayed in the console

### 2. Environment Variable Configuration (`.env.example`)

A complete environment variable configuration template supporting:

```properties
# Default startup preset (automatically overrides BASE_URL and MODEL)
OPEN_AUTOGLM_DEFAULT_PRESET=modelscope

# API Keys for each preset (injected via environment variables, not hardcoded)
OPEN_AUTOGLM_MODELSCOPE_API_KEY=sk-xxx
OPEN_AUTOGLM_ZHIPU_API_KEY=xxx.xxx
OPEN_AUTOGLM_NEWAPI_API_KEY=sk-xxx

# Third-party model prompt engineering
OPEN_AUTOGLM_USE_THIRDPARTY_PROMPT=true
OPEN_AUTOGLM_THIRDPARTY_THINKING=true

# Local OpenAI-compatible service
OPEN_AUTOGLM_LOCAL_OPENAI_BASE_URL=http://127.0.0.1:1234
OPEN_AUTOGLM_LOCAL_OPENAI_ALLOW_EMPTY_KEY=true
```

### 3. Project Configuration (`AGENTS.md`)

A project rules file designed for AI Coding Agents (e.g., Claude Code, Kilo Code):

- **GitHub Repository Info**: Fork/upstream URLs, sync commands
- **Device Configuration**: Xiaomi 14 Ultra USB ID, wireless debugging port
- **API Configuration Table**: Full parameters for ModelScope, Zhipu, and third-party relay
- **Quick Start Commands**: Launch examples for various scenarios
- **Notes**: Important notes on using `--thirdparty` parameter for third-party models

### 4. Third-Party Model Support (`--thirdparty`)

Adaptation for non-native AutoGLM models (e.g., Qwen3-VL):

- **`--thirdparty`**: Enable third-party model prompt engineering
- **`--thirdparty-thinking`**: Enable thinking output (`<think>`/`<answer>` format)
- **`--thirdparty-no-thinking`**: Disable thinking output (pure action output, more compatible with some relay services)
- **`--no-compress-image`**: Disable screenshot compression (preserve original image quality)

---

## Quick Start

### Deploy from GitHub

```powershell
# Clone the repository (LSJ Launcher version)
git clone https://github.com/RusianHu/LSJ-AutoGLM.git
cd LSJ-AutoGLM

# Or clone the official upstream repository
git clone https://github.com/zai-org/Open-AutoGLM.git
cd Open-AutoGLM

# Install dependencies
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# Configure environment variables
cp .env.example .env
# Edit the .env file and fill in your API Key
```

### Method 1: Use the Launcher (Recommended)

1. **Configure environment**: Copy `.env.example` to `.env` and fill in your API Key
2. **Set preset**: Set `OPEN_AUTOGLM_DEFAULT_PRESET` in `.env` (e.g., `modelscope`)
3. **Launch**:

```powershell
python launcher.py
```

The launcher will automatically detect the preset, display system status, and enter the main menu.

### Method 2: Run the GUI

Run from source:

```powershell
python gui_app.py
```

Run the single-file distribution:

```powershell
.\dist\OpenAutoGLM-GUI.exe
```

First-run notes:

1. If there is no [`.env`](.env.example) in the same directory as the exe, the GUI will attempt to create one automatically
2. If the directory is not writable, the settings and diagnostics pages will display a prompt instead of failing silently
3. If the diagnostics page detects missing ADB, ADB Keyboard, scrcpy, or API configuration, it will show the corresponding fix guides and download links

### Method 3: Run `main.py` Directly

```powershell
# Using ModelScope
python main.py --base-url "https://api-inference.modelscope.cn/v1" --model "ZhipuAI/AutoGLM-Phone-9B" --apikey "your-key" "Open WeChat"

# Using a third-party model (e.g., Qwen3-VL)
python main.py --thirdparty --base-url "https://your-api.com/v1" --model "Qwen/Qwen3-VL-235B" --apikey "your-key" "Open Settings"
```

---

## Upstream Sync Log

| Date | Sync Content | Method |
|------|--------------|--------|
| 2026-03-21 | Synced upstream documentation and community resources (WeChat QR code, X account link, Discord link updates) | Selective sync |

See the [Upstream Sync Analysis Report](plans/upstream_sync_analysis.md) for details.

---

## License

This project is open-sourced under the [Apache License 2.0](LICENSE).
