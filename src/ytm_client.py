import socketio
import logging
import json
import os
import time
import threading

# Ensure application-level logging is configured (as it is)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Reduce verbosity of socketio and engineio libraries
logging.getLogger('socketio.client').setLevel(logging.WARNING)
logging.getLogger('socketio.server').setLevel(logging.WARNING)
logging.getLogger('engineio.client').setLevel(logging.WARNING)
logging.getLogger('engineio.server').setLevel(logging.WARNING)

# Define paths relative to this file's location
CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')
# Resolve to an absolute path
CONFIG_PATH = os.path.abspath(CONFIG_PATH)

# Path for the separate YTM authentication token file
YTM_AUTH_CONFIG_PATH = os.path.join(CONFIG_DIR, 'ytm_auth.json')
YTM_AUTH_CONFIG_PATH = os.path.abspath(YTM_AUTH_CONFIG_PATH)

class YTMClient:
    def __init__(self, update_callback=None):
        self.base_url = None
        self.ytm_token = None
        self.load_config() # Loads URL and token
        self.sio = socketio.Client(logger=False, engineio_logger=False)
        self.last_known_track_data = None
        self.is_connected = False
        self._data_lock = threading.Lock()
        self._connection_event = threading.Event()
        self.external_update_callback = update_callback
        self.last_processed_key_data = None # Stores key fields of the last update that triggered a callback

        @self.sio.event(namespace='/api/v1/realtime')
        def connect():
            logging.info(f"Successfully connected to YTM Companion Socket.IO server at {self.base_url} on namespace /api/v1/realtime")
            self.is_connected = True
            self._connection_event.set()

        @self.sio.event(namespace='/api/v1/realtime')
        def connect_error(data):
            logging.error(f"YTM Companion Socket.IO connection failed for namespace /api/v1/realtime: {data}")
            self.is_connected = False
            self._connection_event.set()

        @self.sio.event(namespace='/api/v1/realtime')
        def disconnect():
            logging.info(f"Disconnected from YTM Companion Socket.IO server at {self.base_url} on namespace /api/v1/realtime")
            self.is_connected = False

        @self.sio.on('state-update', namespace='/api/v1/realtime')
        def on_state_update(data):
            logging.debug(f"Received state update from YTM Companion on /api/v1/realtime: {data.get('video',{}).get('title')}")
            
            # Always update the full last_known_track_data for polling purposes
            with self._data_lock:
                self.last_known_track_data = data

            # Extract key fields for deciding if a significant change occurred
            current_key_data = None
            if data and isinstance(data, dict):
                video_info = data.get('video', {})
                player_info = data.get('player', {})
                current_key_data = {
                    'title': video_info.get('title'),
                    'author': video_info.get('author'),
                    'album': video_info.get('album'), # Added album for more robust change detection
                    'trackState': player_info.get('trackState'),
                    'adPlaying': player_info.get('adPlaying', False)
                }

            significant_change_detected = False
            if current_key_data and (self.last_processed_key_data != current_key_data):
                significant_change_detected = True
                self.last_processed_key_data = current_key_data # Update only on significant change
            
            if significant_change_detected and self.external_update_callback:
                logging.info(f"Significant YTM state change detected, calling update callback. Title: {current_key_data.get('title')}")
                try:
                    # Pass the full 'data' object to the callback
                    self.external_update_callback(data) 
                except Exception as cb_ex:
                    logging.error(f"Error executing YTMClient external_update_callback: {cb_ex}")
            elif not significant_change_detected:
                logging.debug(f"YTM state update received but no significant change to key fields. Title: {current_key_data.get('title') if current_key_data else 'N/A'}")

    def load_config(self):
        default_url = "http://localhost:9863"
        self.base_url = default_url # Start with default
        
        # Load base_url from main config.json
        if not os.path.exists(CONFIG_PATH):
            logging.warning(f"Main config file not found at {CONFIG_PATH}. Using default YTM URL: {self.base_url}")
        else:
            try:
                with open(CONFIG_PATH, 'r') as f:
                    loaded_config = json.load(f)
                    music_config = loaded_config.get("music", {})
                    self.base_url = music_config.get("YTM_COMPANION_URL", default_url)
                    if not self.base_url:
                        logging.warning("YTM_COMPANION_URL missing or empty in config.json music section, using default.")
                        self.base_url = default_url
            except json.JSONDecodeError:
                logging.error(f"Error decoding JSON from main config {CONFIG_PATH}. Using default YTM URL.")
            except Exception as e:
                logging.error(f"Error loading YTM_COMPANION_URL from main config {CONFIG_PATH}: {e}. Using default YTM URL.")

        logging.info(f"YTM Companion URL set to: {self.base_url}")

        if self.base_url and self.base_url.startswith("ws://"):
            self.base_url = "http://" + self.base_url[5:]
        elif self.base_url and self.base_url.startswith("wss://"):
            self.base_url = "https://" + self.base_url[6:]

        # Load ytm_token from ytm_auth.json
        self.ytm_token = None # Reset token before trying to load
        if os.path.exists(YTM_AUTH_CONFIG_PATH):
            try:
                with open(YTM_AUTH_CONFIG_PATH, 'r') as f:
                    auth_data = json.load(f)
                    self.ytm_token = auth_data.get("YTM_COMPANION_TOKEN")
                if self.ytm_token:
                    logging.info(f"YTM Companion token loaded from {YTM_AUTH_CONFIG_PATH}.")
                else:
                    logging.warning(f"YTM_COMPANION_TOKEN not found in {YTM_AUTH_CONFIG_PATH}. YTM features will be disabled until token is present.")
            except json.JSONDecodeError:
                logging.error(f"Error decoding JSON from YTM auth file {YTM_AUTH_CONFIG_PATH}. YTM features will be disabled.")
            except Exception as e:
                logging.error(f"Error loading YTM auth config {YTM_AUTH_CONFIG_PATH}: {e}. YTM features will be disabled.")
        else:
            logging.warning(f"YTM auth file not found at {YTM_AUTH_CONFIG_PATH}. Run the authentication script to generate it. YTM features will be disabled.")

    def connect_client(self, timeout=10):
        if not self.ytm_token:
            logging.warning("No YTM token loaded. Cannot connect to Socket.IO. Run authentication script.")
            self.is_connected = False
            return False

        if self.is_connected:
            logging.debug("YTM client already connected.")
            return True

        logging.info(f"Attempting to connect to YTM Socket.IO server: {self.base_url} on namespace /api/v1/realtime")
        auth_payload = {"token": self.ytm_token}

        try:
            self._connection_event.clear()
            self.sio.connect(
                self.base_url,
                transports=['websocket'],
                wait_timeout=timeout,
                namespaces=['/api/v1/realtime'],
                auth=auth_payload
            )
            event_wait_timeout = timeout + 5
            if not self._connection_event.wait(timeout=event_wait_timeout):
                logging.warning(f"YTM Socket.IO connection event not received within {event_wait_timeout}s (connect timeout was {timeout}s).")
                self.is_connected = False
                return False
            logging.info(f"YTM Socket.IO connection successful: {self.is_connected}")
            return self.is_connected
        except socketio.exceptions.ConnectionError as e:
            logging.error(f"YTM Socket.IO connection error: {e}")
            self.is_connected = False
            return False
        except Exception as e:
            logging.error(f"Unexpected error during YTM Socket.IO connection: {e}")
            self.is_connected = False
            return False

    def is_available(self):
        if not self.ytm_token:
            return False
        return self.is_connected

    def get_current_track(self):
        if not self.is_connected:
            return None

        with self._data_lock:
            if self.last_known_track_data:
                return self.last_known_track_data
            else:
                return None

    def disconnect_client(self):
        if self.is_connected:
            self.sio.disconnect()
            logging.info("YTM Socket.IO client disconnected.")
            self.is_connected = False
        else:
            logging.debug("YTM Socket.IO client already disconnected or not connected.")

# Example Usage (for testing - needs to be adapted for Socket.IO async nature)
# if __name__ == '__main__':
# client = YTMClient()
# if client.connect_client(): 
# print("YTM Server is available (Socket.IO).")
# try:
# for _ in range(10): # Poll for a few seconds
# track = client.get_current_track()
# if track:
# print(json.dumps(track, indent=2))
# else:
# print("No track currently playing or error fetching (Socket.IO).")
# time.sleep(2)
# finally:
# client.disconnect_client()
# else:
# print(f"YTM Server not available at {client.base_url} (Socket.IO). Is YTMD running with companion server enabled and token generated?") 