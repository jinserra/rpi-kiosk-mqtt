#!/usr/bin/python3
import paho.mqtt.client as mqtt
import json
import logging
import os
import subprocess
import socket
import threading
import time
import pwd
from rpi_backlight import Backlight
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# --- Configuration ---
MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASS")
DEVICE_NAME = os.getenv("DEVICE_NAME", socket.gethostname())
BACKLIGHT_PATH = os.getenv("BACKLIGHT_PATH", "/sys/class/backlight/panel_backlight@1")
BROWSER_PROCESS = os.getenv("BROWSER_PROCESS", "chromium")

# Feature Toggles
ENABLE_REMOTE_RESTART = os.getenv("ENABLE_REMOTE_RESTART", "true").lower() == "true"
ENABLE_OS_UPDATES = os.getenv("ENABLE_OS_UPDATES", "true").lower() == "true"

# Dynamic URL Parsing (Comma separated in .env)
URL_STRING = os.getenv("KIOSK_URLS", "http://localhost")
KIOSK_URLS = [url.strip() for url in URL_STRING.split(",") if url.strip()]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BrowserManager:
    def __init__(self, process_name, urls):
        self.process = process_name
        self.urls = urls
        
        # 1. Read the desired user from .env
        self.user = os.getenv("BROWSER_USER", "pi")
        
        # 2. Dynamically fetch system data for that user
        try:
            user_info = pwd.getpwnam(self.user)
            self.home_dir = user_info.pw_dir
            self.uid = user_info.pw_uid
        except KeyError:
            logging.error(f"CRITICAL: User '{self.user}' does not exist on this system!")
            self.home_dir = f"/home/{self.user}"
            self.uid = 1000 # Fallback
            
        self.env = os.environ.copy()
        self.env["WAYLAND_DISPLAY"] = "wayland-0"
        
        # 3. Use the dynamic UID for Wayland permissions
        self.env["XDG_RUNTIME_DIR"] = f"/run/user/{self.uid}" 
        self.env["HOME"] = self.home_dir
        self.env["USER"] = self.user

    def manage_state(self, state):
        """Freezes or Thaws the browser."""
        signal = "-CONT" if state.upper() == "ON" else "-STOP"
        subprocess.run(["pkill", signal, self.process], check=False)

    def force_kill_and_restart(self):
        """Force kills the browser for manual restarts."""
        logging.info("Forcing browser termination...")
        subprocess.run(["pkill", "-9", self.process], check=False)
        time.sleep(2) # Give the OS a little extra time to clear Wayland sockets
        self.clean_and_start()

    def clean_and_start(self):
        """Cleans lock files and launches the browser."""
        logging.info(f"Launching Kiosk with {len(self.urls)} URLs as user '{self.user}'...")
        
        # Clear Locks (Using absolute paths)
        config_dir = f"{self.home_dir}/.config/chromium"
        subprocess.run(f"rm -rf {config_dir}/Singleton*", shell=True, check=False)
        
        # Reset Preferences
        pref_path = f"{config_dir}/Default/Preferences"
        if os.path.exists(pref_path):
            subprocess.run(["sed", "-i", 's/"exited_cleanly":false/"exited_cleanly":true/', pref_path], check=False)
            subprocess.run(["sed", "-i", 's/"exit_type":"Crashed"/"exit_type":"Normal"/', pref_path], check=False)

        # Launch Command
        cmd = [
            self.process,
            "--ozone-platform=wayland",
            "--kiosk",
            "--remote-debugging-port=9222",
            "--gcm-registration-url=http://localhost:1/",
            "--password-store=basic",
            "--noerrdialogs",
            "--disable-infobars"
        ] + self.urls
        
        try:
            # Drop root privileges just for this process
            subprocess.Popen(
                cmd, 
                env=self.env, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                user=self.user
            )
        except Exception as e:
            logging.error(f"Failed to start browser: {e}")

    def monitor_health(self):
        """Monitors browser health and restarts if it crashes."""
        while True:
            check = subprocess.run(["pgrep", self.process], capture_output=True)
            if check.returncode != 0:
                logging.warning(f"{self.process} not found. Auto-restarting...")
                self.clean_and_start()
            time.sleep(30)

class SystemManager:
    @staticmethod
    def get_update_count():
        try:
            cmd = "apt-get -s upgrade | grep -P '^\\d+ upgraded' | cut -d' ' -f1"
            result = subprocess.check_output(cmd, shell=True).decode().strip()
            return int(result) if result else 0
        except Exception:
            return 0

    @staticmethod
    def apply_updates():
        logging.info("Starting OS Update process. This may take a few minutes...")
        try:
            subprocess.run(["apt-get", "upgrade", "-y"], check=True)
            logging.info("OS Updates applied successfully.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to apply OS updates: {e}")

class KioskController:
    def __init__(self):
        self.backlight = Backlight(backlight_sysfs_path=BACKLIGHT_PATH)
        self.browser = BrowserManager(BROWSER_PROCESS, KIOSK_URLS)
        self.system = SystemManager()
        
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        self.base_topic = f"homeassistant/light/{DEVICE_NAME}"
        self.restart_topic = f"homeassistant/button/{DEVICE_NAME}/browser_restart/set"
        self.update_topic = f"homeassistant/button/{DEVICE_NAME}/apply_updates/set"

    def send_discovery(self):
        # 1. Screen Light Entity (Always Enabled)
        config = {
            "name": f"{DEVICE_NAME} Screen",
            "unique_id": f"{DEVICE_NAME}_screen",
            "command_topic": f"{self.base_topic}/set",
            "state_topic": f"{self.base_topic}/state",
            "brightness_command_topic": f"{self.base_topic}/brightness/set",
            "brightness_state_topic": f"{self.base_topic}/brightness/state",
            "device": {"identifiers": [DEVICE_NAME], "name": DEVICE_NAME}
        }
        self.client.publish(f"{self.base_topic}/config", json.dumps(config), retain=True)

        # 2. Browser Restart Feature
        if ENABLE_REMOTE_RESTART:
            button_config = {
                "name": f"{DEVICE_NAME} Restart Browser",
                "unique_id": f"{DEVICE_NAME}_restart_browser",
                "command_topic": self.restart_topic,
                "icon": "mdi:web-refresh",
                "device": {"identifiers": [DEVICE_NAME]}
            }
            self.client.publish(f"homeassistant/button/{DEVICE_NAME}/browser_restart/config", json.dumps(button_config), retain=True)

        # 3. OS Updates Feature
        if ENABLE_OS_UPDATES:
            update_sensor = {
                "name": f"{DEVICE_NAME} Pending Updates",
                "unique_id": f"{DEVICE_NAME}_updates",
                "state_topic": f"homeassistant/sensor/{DEVICE_NAME}/updates",
                "unit_of_measurement": "packages",
                "icon": "mdi:package-up",
                "device": {"identifiers": [DEVICE_NAME]}
            }
            self.client.publish(f"homeassistant/sensor/{DEVICE_NAME}/updates/config", json.dumps(update_sensor), retain=True)
            
            update_button = {
                "name": f"{DEVICE_NAME} Apply Updates",
                "unique_id": f"{DEVICE_NAME}_apply_updates",
                "command_topic": self.update_topic,
                "icon": "mdi:cellphone-arrow-down",
                "device": {"identifiers": [DEVICE_NAME]}
            }
            self.client.publish(f"homeassistant/button/{DEVICE_NAME}/apply_updates/config", json.dumps(update_button), retain=True)

    def on_connect(self, client, userdata, flags, rc, properties=None):
        logging.info(f"Connected to MQTT as {DEVICE_NAME}")
        self.send_discovery()
        client.subscribe(f"{self.base_topic}/#")
        if ENABLE_REMOTE_RESTART:
            client.subscribe(self.restart_topic)
        if ENABLE_OS_UPDATES:
            client.subscribe(self.update_topic)

    def on_message(self, client, userdata, msg):
        payload = msg.payload.decode().upper()
        
        # Handle Screen Toggle
        if msg.topic.endswith("/set") and "restart" not in msg.topic and "updates" not in msg.topic:
            is_on = (payload == "ON")
            self.backlight.power = is_on
            self.browser.manage_state(payload)
            client.publish(f"{self.base_topic}/state", payload, retain=True)
            
        # Handle Remote Restart Trigger
        elif msg.topic == self.restart_topic and ENABLE_REMOTE_RESTART:
            logging.info("Remote browser restart requested.")
            self.browser.force_kill_and_restart()

        # Handle OS Updates Trigger
        elif msg.topic == self.update_topic and ENABLE_OS_UPDATES:
            logging.info("OS Update requested. Spawning background thread...")
            threading.Thread(target=self.system.apply_updates, daemon=True).start()

    def update_loop(self):
        while True:
            count = self.system.get_update_count()
            self.client.publish(f"homeassistant/sensor/{DEVICE_NAME}/updates", count, retain=True)
            time.sleep(3600)

    def run(self):
        self.client.connect(MQTT_BROKER, 1883, 60)
        threading.Thread(target=self.browser.monitor_health, daemon=True).start()
        if ENABLE_OS_UPDATES:
            threading.Thread(target=self.update_loop, daemon=True).start()
        self.client.loop_forever()

if __name__ == "__main__":
    KioskController().run()