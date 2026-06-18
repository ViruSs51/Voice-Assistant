# 🎙️ Voice Assistant

A local AI voice assistant built with **ESP32**, **Whisper**, **Ollama**, and **FastAPI**.

The ESP32 continuously streams microphone audio to a local server over LAN. The server detects a wake word, converts speech to text, generates a response using an LLM, converts the response back to speech, and streams the audio back to the ESP32 speaker.

Everything runs locally except Text-to-Speech, which currently uses Google TTS.

---

## ✨ Features

* Wake word detection (`"Okay Bro"`)
* Speech-to-Text using Whisper
* Local LLM responses using Ollama
* Text-to-Speech generation
* Real-time audio streaming
* ESP32 microphone and speaker support
* FastAPI WebSocket communication
* Configurable server settings

---

## 🏗️ Project Structure

```text
Voice-Assistant/
│
├── src/
│   └── main.cpp              # ESP32 firmware
│
├── server/
│   ├── server.py             # Main server
│   │
│   ├── settings/
│   │   └── config.json       # Server configuration
│   │
│   ├── data/
│   │   ├── command.wav       # Recorded command
│   │   ├── response.mp3      # Generated response
│   │   └── response.wav      # Converted response
│   │
│   └── server.log
│
├── requirements.txt
├── platformio.ini
└── README.md
```

---

# 🔧 Hardware Requirements

## ESP32

Any ESP32 board with:

* Wi-Fi support
* I2S support
* Built-in DAC support

---

## Microphone

Tested with:

* INMP441

### Wiring

| INMP441 | ESP32   |
| ------- | ------- |
| VDD     | 3V3     |
| GND     | GND     |
| SCK     | GPIO 14 |
| WS      | GPIO 15 |
| SD      | GPIO 32 |
| L/R     | GND     |

The microphone is configured as:

```cpp
I2S_CHANNEL_FMT_ONLY_LEFT
```

---

## Audio Amplifier

Tested with:

* PAM8403

### Wiring

| PAM8403 | ESP32   |
| ------- | ------- |
| R Input | GPIO 25 |
| VCC     | 5V      |
| GND     | GND     |

Speaker should be connected to the amplifier output.

Optional:

* 1µF – 10µF capacitor in series between GPIO25 and amplifier input.

---

# 💻 Software Requirements

Install:

* Python 3.10+
* PlatformIO
* Ollama
* ffmpeg

---

## Python Dependencies

Create a virtual environment:

```bash
python -m venv venv
```

Activate it:

### Windows

```bash
venv\Scripts\activate
```

### Linux

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Install Ollama

Install Ollama from:

```text
https://ollama.com
```

Pull the model you want to use:

```bash
ollama pull llama3
```

You can later change the model inside:

```text
server/settings/config.json
```

---

## Install ffmpeg

ffmpeg is required for audio conversion.

### Windows

Download from:

```text
https://ffmpeg.org/download.html
```

Make sure `ffmpeg` is available from the command line:

```bash
ffmpeg -version
```

---

# ⚙️ Configuration

Edit:

```text
server/settings/config.json
```

Example:

```json
{
    "llm_model": "llama3",
    "whisper_device_type": "cpu",
    "llm_system_prompt": "You are a helpful assistant."
}
```

---

# 📡 ESP32 Configuration

Open:

```cpp
src/main.cpp
```

Set your network credentials:

```cpp
const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASSWORD";
```

Set your server address:

```cpp
const char* server_ip = "192.168.1.100";
```

---

# 🚀 Getting Started

## 1. Upload Firmware

Build and upload the firmware to the ESP32 using PlatformIO.

---

## 2. Start the Server

Navigate to:

```bash
cd server
```

Run:

```bash
python server.py
```

---

## 3. Configure the Server

Inside the terminal:

```text
help
```

Available commands:

```text
run
conf
update <parameter>
quit
```

### Show current configuration

```text
conf
```

### Update a configuration value

```text
update whisper_device_type
```

### Start the server

```text
run
```

---

# 🔄 How It Works

```text
User Speech
     │
     ▼
ESP32 Microphone
     │
     ▼
WebSocket Stream
     │
     ▼
Whisper
(Speech → Text)
     │
     ▼
Ollama
(LLM Response)
     │
     ▼
Google TTS
(Text → Speech)
     │
     ▼
ffmpeg
(Audio Conversion)
     │
     ▼
ESP32 Speaker
```

---

# 📝 Logs

Server logs are stored in:

```text
server/server.log
```

Useful for debugging:

* Wi-Fi issues
* WebSocket communication
* Whisper transcription
* Ollama responses
* Audio generation


---

# 📜 License

This project is provided for educational and personal use.

