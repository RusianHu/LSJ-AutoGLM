# Open-AutoGLM

Open-AutoGLM is an open-source project that provides an easy-to-use interface for controlling Android devices using natural language commands. It leverages advanced vision-language models to understand the device screen and execute actions like tapping, swiping, and typing.

## Features

- **Natural Language Control**: Control your Android device using simple text commands.
- **Vision-Language Model**: Uses a powerful vision-language model to understand the screen content.
- **Multi-Device Support**: Supports controlling multiple devices simultaneously.
- **Extensible**: Easily add support for new apps and actions.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/zai-org/Open-AutoGLM.git
    cd Open-AutoGLM
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Install ADB**:
    -   **Windows**: Download the Android SDK Platform-Tools and add `adb` to your PATH.
    -   **macOS**: `brew install android-platform-tools`
    -   **Linux**: `sudo apt-get install android-tools-adb`

4.  **Connect your device**:
    -   Enable **Developer Options** and **USB Debugging** on your Android device.
    -   Connect your device to your computer via USB.
    -   Run `adb devices` to verify the connection.

5.  **Install ADB Keyboard**:
    -   Download [ADBKeyboard.apk](https://github.com/senzhk/ADBKeyBoard/blob/master/ADBKeyboard.apk).
    -   Install it on your device: `adb install ADBKeyboard.apk`.
    -   Set it as the default input method in your device settings.

## Usage

1.  **Start the model server**:
    -   You can use a local model server (e.g., vLLM) or a remote API.
    -   Ensure the model server provides an OpenAI-compatible API.

2.  **Run the agent**:
    ```bash
    python main.py --base-url http://localhost:8000/v1 --model autoglm-phone-9b
    ```

    You can also specify a task directly:
    ```bash
    python main.py --base-url http://localhost:8000/v1 --model autoglm-phone-9b "Open Settings and turn on Wi-Fi"
    ```

## Configuration

You can configure the agent using command-line arguments or environment variables.

-   `--base-url`: The base URL of the model API (default: `http://localhost:8000/v1`).
-   `--model`: The name of the model to use (default: `autoglm-phone-9b`).
-   `--device-id`: The serial number of the device to control (optional).
-   `--lang`: The language for the system prompt (`cn` or `en`, default: `cn`).

## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.