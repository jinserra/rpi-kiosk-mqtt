#!/usr/bin/python3
import paho.mqtt.client as mqtt
import json
import logging
import os
import subprocess
from rpi_backlight import Backlight
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# Configuration from environment variables
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")
BACKLIGHT_PATH = os.getenv("BACKLIGHT_PATH", "/sys/class/backlight/rpi_backlight")
BROWSER_PROCESS = os.getenv("BROWSER_PROCESS", "chromium")

# Topics
BASE_TOPIC = "homeassistant/pi_screen"
DISCOVERY_TOPIC = "homeassistant/light/pi_screen/config"
COMMAND_TOPIC = f"{BASE_TOPIC}/set"
BRIGHTNESS_SET_TOPIC = f"{BASE_TOPIC}/brightness/set"
STATE_TOPIC = f"{BASE_TOPIC}/state"
BRIGHTNESS_STATE_TOPIC = f"{BASE_TOPIC}/brightness/state"
AVAILABILITY_TOPIC = f"{BASE_TOPIC}/availability"

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Backlight with custom path
try:
    backlight = Backlight(backlight_sysfs_path=BACKLIGHT_PATH)
except Exception as e:
    logging.error(f"Failed to initialize backlight at {BACKLIGHT_PATH}: {e}")
    exit(1)

def manage_browser(state):
    """Suspends (STOP) or Resumes (CONT) the browser process."""
    try:
        # Check if browser is running
        check = subprocess.run(["pgrep", BROWSER_PROCESS], capture_output=True)
        if check.returncode != 0:
            return

        if state.upper() == "ON":
            logging.info(f"Resuming {BROWSER_PROCESS}...")
            subprocess.run(["pkill", "-CONT", BROWSER_PROCESS], check=False)
        else:
            logging.info(f"Suspending {BROWSER_PROCESS}...")
            subprocess.run(["pkill", "-STOP", BROWSER_PROCESS], check=False)
    except Exception as e:
        logging.error(f"Process management error: {e}")

def send_discovery(client):
    """MQTT Discovery for Home Assistant."""
    config_payload = {
        "name": "Raspberry Pi Screen",
        "unique_id": "rpi_screen_001",
        "command_topic": COMMAND_TOPIC,
        "state_topic": STATE_TOPIC,
        "brightness_command_topic": BRIGHTNESS_SET_TOPIC,
        "brightness_state_topic": BRIGHTNESS_STATE_TOPIC,
        "availability_topic": AVAILABILITY_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
        "brightness_scale": 100,
        "device": {
            "identifiers": ["rpi_display_01"],
            "name": "Pi Kiosk",
            "model": "Official Touchscreen",
            "manufacturer": "Raspberry Pi"
        }
    }
    client.publish(DISCOVERY_TOPIC, json.dumps(config_payload), retain=True)

def update_ha_state(client):
    pwr = "ON" if backlight.power else "OFF"
    client.publish(STATE_TOPIC, pwr, retain=True)
    client.publish(BRIGHTNESS_STATE_TOPIC, backlight.brightness, retain=True)

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logging.info("Connected to MQTT Broker")
        client.publish(AVAILABILITY_TOPIC, "online", retain=True)
        send_discovery(client)
        update_ha_state(client)
        client.subscribe([(COMMAND_TOPIC, 0), (BRIGHTNESS_SET_TOPIC, 0)])
    else:
        logging.error(f"Connection failed: {rc}")

def on_message(client, userdata, msg):
    payload = msg.payload.decode()
    try:
        if msg.topic == COMMAND_TOPIC:
            new_state = payload.upper()
            backlight.power = (new_state == "ON")
            manage_browser(new_state)
            logging.info(f"Screen Power: {new_state}")
        elif msg.topic == BRIGHTNESS_SET_TOPIC:
            val = int(float(payload))
            backlight.brightness = val
            logging.info(f"Brightness: {val}%")
        update_ha_state(client)
    except Exception as e:
        logging.error(f"Action error: {e}")

# --- Client Setup ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USER, MQTT_PASS)

# Last Will and Testament
client.will_set(AVAILABILITY_TOPIC, "offline", retain=True)

client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, 1883, 60)
try:
    client.loop_forever()
except KeyboardInterrupt:
    subprocess.run(["pkill", "-CONT", BROWSER_PROCESS], check=False)
    client.publish(AVAILABILITY_TOPIC, "offline", retain=True)
