import time
import logging
from typing import Dict, Any
from src.clock import Clock
from src.weather_manager import WeatherManager
from src.display_manager import DisplayManager
from src.config_manager import ConfigManager
from src.stock_manager import StockManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DisplayController:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.display_manager = DisplayManager(self.config.get('display', {}))
        self.clock = Clock(display_manager=self.display_manager)
        self.weather = WeatherManager(self.config, self.display_manager)
        self.stocks = StockManager(self.config, self.display_manager)
        self.current_display = 'clock'
        self.weather_mode = 'current'  # current, hourly, or daily
        self.last_switch = time.time()
        self.force_clear = True  # Start with a clear screen
        self.update_interval = 0.5  # Slower updates for better stability
        self.display_durations = self.config['display'].get('display_durations', {
            'clock': 15,
            'weather': 15,
            'stocks': 45,
            'hourly_forecast': 15,
            'daily_forecast': 15
        })
        logger.info("DisplayController initialized with display_manager: %s", id(self.display_manager))

    def get_current_duration(self) -> int:
        """Get the duration for the current display mode."""
        if self.current_display == 'weather':
            if self.weather_mode == 'hourly':
                return self.display_durations.get('hourly_forecast', 15)
            elif self.weather_mode == 'daily':
                return self.display_durations.get('daily_forecast', 15)
            return self.display_durations.get('weather', 15)
        return self.display_durations.get(self.current_display, 15)

    def run(self):
        """Run the display controller, switching between displays."""
        try:
            while True:
                current_time = time.time()
                
                # Check if we need to switch display mode
                if current_time - self.last_switch > self.get_current_duration():
                    # Cycle through: clock -> weather (current) -> weather (hourly) -> weather (daily) -> stocks
                    if self.current_display == 'clock':
                        self.current_display = 'weather'
                        self.weather_mode = 'current'
                    elif self.current_display == 'weather':
                        if self.weather_mode == 'current':
                            self.weather_mode = 'hourly'
                        elif self.weather_mode == 'hourly':
                            self.weather_mode = 'daily'
                        else:  # daily
                            if self.config.get('stocks', {}).get('enabled', False):
                                self.current_display = 'stocks'
                            else:
                                self.current_display = 'clock'
                    else:  # stocks
                        self.current_display = 'clock'
                    
                    logger.info(f"Switching display to: {self.current_display} {self.weather_mode if self.current_display == 'weather' else ''}")
                    self.last_switch = current_time
                    self.force_clear = True
                    self.display_manager.clear()  # Ensure clean transition

                # Display current screen
                try:
                    if self.current_display == 'clock':
                        self.clock.display_time(force_clear=self.force_clear)
                    elif self.current_display == 'weather':
                        if self.weather_mode == 'current':
                            self.weather.display_weather(force_clear=self.force_clear)
                        elif self.weather_mode == 'hourly':
                            self.weather.display_hourly_forecast(force_clear=self.force_clear)
                        else:  # daily
                            self.weather.display_daily_forecast(force_clear=self.force_clear)
                    else:  # stocks
                        self.stocks.display_stocks(force_clear=self.force_clear)
                except Exception as e:
                    logger.error(f"Error updating display: {e}")
                    time.sleep(1)  # Wait a bit before retrying
                    continue

                # Reset force clear flag after use
                self.force_clear = False

                # Sleep between updates
                time.sleep(self.update_interval)

        except KeyboardInterrupt:
            print("\nDisplay stopped by user")
        finally:
            self.display_manager.cleanup()

def main():
    controller = DisplayController()
    controller.run()

if __name__ == "__main__":
    main() 