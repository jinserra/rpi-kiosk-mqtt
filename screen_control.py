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

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")

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
backlight = Backlight(backlight_sysfs_path='/sys/class/backlight/panel_backlight@1')

def manage_chromium(state):
    """
    Suspends (STOP) or Resumes (CONT) Chromium processes.
    STOP: Process stays in RAM but uses 0% CPU.
    CONT: Process resumes exactly where it left off.
    """
    try:
        # Check if chromium is even running to avoid pkill errors
        check = subprocess.run(["pgrep", "chromium"], capture_output=True)
        if check.returncode != 0:
            logging.warning("Chromium not running; nothing to suspend/resume.")
            return

        if state.upper() == "ON":
            logging.info("Sending SIGCONT to Chromium (Resuming)...")
            subprocess.run(["pkill", "-CONT", "chromium"], check=False)
        else:
            logging.info("Sending SIGSTOP to Chromium (Suspending)...")
            subprocess.run(["pkill", "-STOP", "chromium"], check=False)
    except Exception as e:
        logging.error(f"Error managing Chromium: {e}")

def send_discovery(client):
    """Publishes the discovery payload to Home Assistant."""
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
            "name": "Pi Dashboard",
            "model": "Official Touchscreen",
            "manufacturer": "Raspberry Pi"
        }
    }
    client.publish(DISCOVERY_TOPIC, json.dumps(config_payload), retain=True)
    logging.info("Discovery payload sent.")

def update_ha_state(client):
    """Syncs hardware state back to HA."""
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
            # Toggle physical hardware
            backlight.power = (new_state == "ON")
            # Toggle Chromium process
            manage_chromium(new_state)
            logging.info(f"System State: {new_state}")
            
        elif msg.topic == BRIGHTNESS_SET_TOPIC:
            val = int(float(payload))
            backlight.brightness = val
            logging.info(f"Brightness: {val}%")
        
        update_ha_state(client)
    except Exception as e:
        logging.error(f"Hardware/Process Error: {e}")

# --- Initialize ---
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.will_set(AVAILABILITY_TOPIC, "offline", retain=True)

client.on_connect = on_connect
client.on_message = on_message

logging.info(f"Connecting to {MQTT_BROKER}...")
client.connect(MQTT_BROKER, 1883, 60)

try:
    client.loop_forever() 
except KeyboardInterrupt:
    # Safety: Always resume Chromium if the script is killed
    subprocess.run(["pkill", "-CONT", "chromium"], check=False)
    client.publish(AVAILABILITY_TOPIC, "offline", retain=True)
    logging.info("Shutting down...")
