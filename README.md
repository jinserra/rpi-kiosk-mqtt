# rpi-kiosk-mqtt
A Python script to manage a Raspberry Pi Official Touchscreen via MQTT, with process suspension.

## 🌟 Features
- **MQTT Backlight Control**: Turn the screen ON/OFF and adjust brightness (0-100%) via Home Assistant.
- **Chromium Suspension**: Automatically sends `SIGSTOP` to Chromium when the screen is off to reduce CPU usage and heat, and `SIGCONT` to resume.
- **Home Assistant Discovery**: Automatically adds the screen as a 'Light' entity via MQTT Discovery.
- **Hardware Agnostic**: Supports both legacy (`rpi_backlight`) and new KMS (`panel_backlight@1`) display drivers.

## 📋 Prerequisites
- Raspberry Pi with the **Official Touchscreen**.
- Raspberry Pi OS (Trixie).
- Python 3.x.

### Required Libraries
```bash
pip3 install paho-mqtt rpi-backlight python-dotenv
