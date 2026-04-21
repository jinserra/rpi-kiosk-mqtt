# rpi-kiosk-mqtt
A Python script to manage a Raspberry Pi Official Touchscreen via MQTT, with process suspension.

## Origin
- I built a kisok to display a Home Assistant dashboard, but figured that I would save resources by turning off the display when I'm not present.
- I then added additional tabs to be displayed and automatically rotate what is shown. However, now with rotating tab the requests were still being sent even if the screen was off, so I wanted to suspend the browser along with turning off the screen.

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
```

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
