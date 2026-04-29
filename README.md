# rpi-kiosk-mqtt
A Python script to manage a Raspberry Pi Official Touchscreen via MQTT, with process suspension.

## 💡 Origin
- Built a kiosk to display a Home Assistant dashboard using available parts at home
- Iterative improvements - Save resources by turning on/off the display based upon presence.
- Rotate through multiple tabs, and suspend the browser when turning off the screen.

## 🌟 Features
- **MQTT Backlight Control**: Turn the screen ON/OFF and adjust brightness (0-100%) via Home Assistant.
- **Chromium Suspension**: Automatically sends `SIGSTOP` to Chromium when the screen is off to reduce CPU usage and heat, and `SIGCONT` to resume.
- **Remote Browser Management**: Remotely force-restart the Chromium process directly from a Home Assistant button entity.
- **OS Update Management**: Tracks pending `apt` updates via an MQTT sensor and allows applying them remotely via a Home Assistant button.
- **Home Assistant Discovery**: Automatically adds the screen, update sensors, and restart buttons via MQTT Discovery (dynamically named based on your Pi's hostname).
- **Hardware Agnostic**: Supports both legacy (`rpi_backlight`) and new KMS (`panel_backlight@1`) display drivers.

## 📋 Prerequisites
- Raspberry Pi with the **Official Raspberry Pi Touch Display 2**.
- Raspberry Pi OS (Trixie).
- Python 3.x.
- Browser (I used Chromium)
- [Revolver Tab Rotator](https://chromewebstore.google.com/detail/revolver-tab-rotator/jocjflhaheogmbkdnbahnmeokeihpcdc) extension (Optional)

### Required Libraries
paho-mqtt rpi-backlight python-dotenv

## 🤖 Home Assistant Automation
To integrate this with your presence sensors, you can use the following automation. This example uses `mode: restart` to ensure the screen reacts immediately to new motion events.

```yaml
alias: "Screen: Office Presence Control"
description: "Manages Pi screen power based on presence"
trigger:
  - platform: state
    entity_id: binary_sensor.your_presence_sensor
    to: "on"
    id: "motion"
  - platform: state
    entity_id: binary_sensor.your_presence_sensor
    to: "off"
    for:
      minutes: 3
    id: "no_motion"
action:
  - choose:
      - conditions:
          - condition: trigger
            id: "motion"
        sequence:
          - action: light.turn_on
            target:
              entity_id: light.pi_dashboard_screen
      - conditions:
          - condition: trigger
            id: "no_motion"
        sequence:
          - action: light.turn_off
            target:
              entity_id: light.pi_dashboard_screen
mode: restart
```

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/jinserra/rpi-kiosk-mqtt.git
cd rpi-kiosk-mqtt
```

### 2. Install Dependencies
#### Option A: Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Option B: System-wide Installation
```bash
sudo pip3 install -r requirements.txt --break-system-packages
```
### 3. Create a .env file from the example:
```bash
cp .env.example .env
vi .env
```
### 4. Configure your MQTT broker details and the correct BACKLIGHT_PATH.
For Trixie/KMS drivers, use: /sys/class/backlight/panel_backlight@1

### 5. Setup the Systemd Service
#### Open the service file and replace `YOUR_USERNAME` with your actual Pi username:
```bash
vi pi-screen.service
```
#### Copy the included service file to the system directory:
```bash
sudo cp pi-screen.service /etc/systemd/system/
```
#### Reload the daemon and enable the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pi-screen.service
sudo systemctl start pi-screen.service
```

### 6. Verify service running
```bash
sudo journalctl -u pi-screen.service -f
```
