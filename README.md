# Open-AutoGLM (老司机启动器)

这是 Open-AutoGLM 的老司机启动器版本，包含针对本地开发环境的特殊更改和优化。

## 📚 官方文档链接

原项目的详细说明文档已被重命名，请查阅以下链接获取完整的使用指南和项目介绍：

- **[📄 官方说明文档 (Original README)](README_official.md)**
- [📄 English README](README_en.md)
- [📄 Agent 规则说明 (AGENTS.md)](AGENTS.md)

---

## ✨ 定制化更改说明

本版本在原版基础上进行了以下修改，以适配特定的开发流程和硬件环境：

### 1. 启动器增强 (`launcher.py`)

优化了交互式启动器，增加了 **自动加载 API 预设** 的功能，提高了启动效率。

- **功能描述**: 启动时自动读取环境变量 `OPEN_AUTOGLM_DEFAULT_PRESET`。
- **逻辑**: 如果检测到有效的预设名称（如 `modelscope`, `zhipu`, `newapi`, `local_openai`），程序会自动应用相关的 `Base URL`、`Model` 以及 `API Key` 配置，跳过手动选择步骤。

### 2. 配置文件更新 (`.env.example`)

同步更新了配置文件模板，添加了默认预设的支持：

```properties
# 默认启动预设 (modelscope / zhipu / newapi / local_openai)
# 设置此项会自动覆盖上面的 BASE_URL 和 MODEL，并加载对应的 API Key
# OPEN_AUTOGLM_DEFAULT_PRESET=modelscope
```

### 3. 文档微调 (`AGENTS.md`)

- 更新了关于第三方模型 (`--thirdparty`) 参数的描述，使其更加准确。
- 强调了使用 `--thirdparty` 参数对于非 AutoGLM 原生模型的重要性。

## 🚀 快速使用

1. **配置环境**: 复制 `.env.example` 为 `.env`，并填入你的 API Key。
2. **设置预设**: 在 `.env` 中取消注释并设置 `OPEN_AUTOGLM_DEFAULT_PRESET`（例如设为 `modelscope`）。
3. **启动**:

```powershell
python launcher.py
```

启动器将自动识别预设并进入准备就绪状态。