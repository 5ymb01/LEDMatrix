import spotipy
from spotipy.oauth2 import SpotifyOAuth
import logging
import json
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define paths relative to this file's location
CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', 'config')
SECRETS_PATH = os.path.join(CONFIG_DIR, 'config_secrets.json')
SPOTIFY_AUTH_CACHE_PATH = os.path.join(CONFIG_DIR, 'spotify_auth.json') # Explicit cache path for token

# Resolve to absolute paths
CONFIG_DIR = os.path.abspath(CONFIG_DIR)
SECRETS_PATH = os.path.abspath(SECRETS_PATH)
SPOTIFY_AUTH_CACHE_PATH = os.path.abspath(SPOTIFY_AUTH_CACHE_PATH)

class SpotifyClient:
    def __init__(self):
        self.client_id = None
        self.client_secret = None
        self.redirect_uri = None
        self.scope = "user-read-currently-playing user-read-playback-state"
        self.sp = None
        self.load_credentials()
        if self.client_id and self.client_secret and self.redirect_uri:
            # Attempt to authenticate once using the cache path
            self._authenticate()
        else:
            logging.warning("Spotify credentials not loaded. Spotify client will not be functional.")

    def load_credentials(self):
        if not os.path.exists(SECRETS_PATH):
            logging.error(f"Secrets file not found at {SECRETS_PATH}. Spotify features will be unavailable.")
            return

        try:
            with open(SECRETS_PATH, 'r') as f:
                secrets = json.load(f)
                music_secrets = secrets.get("music", {})
                self.client_id = music_secrets.get("SPOTIFY_CLIENT_ID")
                self.client_secret = music_secrets.get("SPOTIFY_CLIENT_SECRET")
                self.redirect_uri = music_secrets.get("SPOTIFY_REDIRECT_URI")
                if not all([self.client_id, self.client_secret, self.redirect_uri]):
                    logging.warning("One or more Spotify credentials missing in config_secrets.json. Spotify will be unavailable.")
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {SECRETS_PATH}. Spotify will be unavailable.")
        except Exception as e:
            logging.error(f"Error loading Spotify credentials: {e}. Spotify will be unavailable.")

    def _authenticate(self):
        """Initializes Spotipy with SpotifyOAuth, relying on a cached token."""
        if not self.client_id or not self.client_secret or not self.redirect_uri:
            logging.warning("Cannot authenticate Spotify: credentials missing.")
            return

        # ---- START DIAGNOSTIC BLOCK ----
        logging.info(f"Attempting to use cache path: {SPOTIFY_AUTH_CACHE_PATH}")
        if os.path.exists(SPOTIFY_AUTH_CACHE_PATH):
            logging.info(f"Cache file {SPOTIFY_AUTH_CACHE_PATH} EXISTS.")
            if os.access(SPOTIFY_AUTH_CACHE_PATH, os.R_OK):
                logging.info(f"Cache file {SPOTIFY_AUTH_CACHE_PATH} IS R_OK readable by UID {os.geteuid()}.")
                try:
                    with open(SPOTIFY_AUTH_CACHE_PATH, 'r') as f_test:
                        content = f_test.read()
                        logging.info(f"Cache file content (first 100 chars): '{content[:100]}'")
                        if not content.strip():
                            logging.warning("Cache file IS EMPTY or whitespace only upon manual inspection!")
                except Exception as e_test:
                    logging.error(f"Error during manual read test of cache file: {e_test}")
            else:
                logging.warning(f"Cache file {SPOTIFY_AUTH_CACHE_PATH} is NOT R_OK readable by UID {os.geteuid()}.")
            
            # Additionally, let's check permissions with stat
            try:
                stat_info = os.stat(SPOTIFY_AUTH_CACHE_PATH)
                logging.info(f"Cache file stat info: UID={stat_info.st_uid}, GID={stat_info.st_gid}, Mode={oct(stat_info.st_mode)}")
            except Exception as e_stat:
                logging.error(f"Error getting stat info for cache file: {e_stat}")
        else:
            logging.warning(f"Cache file {SPOTIFY_AUTH_CACHE_PATH} does NOT exist when _authenticate is called.")
        # ---- END DIAGNOSTIC BLOCK ----

        try:
            # Use the explicit cache path. Spotipy will try to load/refresh token from here.
            auth_manager = SpotifyOAuth(
                client_id=self.client_id,
                client_secret=self.client_secret,
                redirect_uri=self.redirect_uri,
                scope=self.scope,
                cache_path=SPOTIFY_AUTH_CACHE_PATH, # Use the defined cache path
                open_browser=False
            )
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
            
            # Try making a lightweight call to verify if the token from cache is valid or can be refreshed.
            self.sp.current_user() # This will raise an exception if token is invalid/expired and cannot be refreshed.
            logging.info("Spotify client initialized and authenticated using cached token.")
        except Exception as e:
            logging.warning(f"Spotify client initialization/authentication failed: {e}. Run authenticate_spotify.py if needed.")
            self.sp = None # Ensure sp is None if auth fails

    def is_authenticated(self):
        """Checks if the client is currently considered authenticated and usable."""
        return self.sp is not None # Relies on _authenticate setting sp to None on failure

    # Removed get_auth_url method - this is now handled by authenticate_spotify.py

    def get_current_track(self):
        """Fetches the currently playing track from Spotify."""
        if not self.is_authenticated(): # Check our internal state
            # Do not attempt to re-authenticate here. User must run authenticate_spotify.py
            # logging.debug("Spotify not authenticated. Cannot fetch track. Run authenticate_spotify.py if needed.")
            return None

        try:
            track_info = self.sp.current_playback()
            if track_info and track_info['item']:
                 return track_info
            else:
                 return None 
        except spotipy.exceptions.SpotifyException as e:
            logging.error(f"Spotify API error when fetching current track: {e}")
            # If it's an auth error (e.g. token revoked server-side), set sp to None so is_authenticated reflects it.
            if e.http_status == 401 or e.http_status == 403: 
                logging.warning("Spotify authentication error (token may be revoked or expired). Please re-run authenticate_spotify.py.")
                self.sp = None # Mark as not authenticated
            return None
        except Exception as e: # Catch other potential errors (network, etc.)
            logging.error(f"Unexpected error fetching current track from Spotify: {e}")
            return None

# Example Usage (for testing, adapt to new auth flow)
# if __name__ == '__main__':
#     # First, ensure you have run authenticate_spotify.py successfully as the user.
#     client = SpotifyClient()
#     if client.is_authenticated():
#         print("Spotify client is authenticated.")
#         track = client.get_current_track()
#         if track:
#             print(json.dumps(track, indent=2))
#         else:
#             print("No track currently playing or error fetching.")
#     else:
#         print("Spotify client not authenticated. Please run src/authenticate_spotify.py as the correct user.") 