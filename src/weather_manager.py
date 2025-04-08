import requests
import time
from datetime import datetime
from typing import Dict, Any, List
from PIL import Image, ImageDraw

class WeatherManager:
    # Weather condition to larger colored icons (we'll use these as placeholders until you provide custom ones)
    WEATHER_ICONS = {
        'Clear': '🌞',      # Larger sun with rays
        'Clouds': '☁️',     # Cloud
        'Rain': '🌧️',      # Rain cloud
        'Snow': '❄️',      # Snowflake
        'Thunderstorm': '⛈️', # Storm cloud
        'Drizzle': '🌦️',    # Sun behind rain cloud
        'Mist': '🌫️',      # Fog
        'Fog': '🌫️',       # Fog
        'Haze': '🌫️',      # Fog
        'Smoke': '🌫️',     # Fog
        'Dust': '🌫️',      # Fog
        'Sand': '🌫️',      # Fog
        'Ash': '🌫️',       # Fog
        'Squall': '💨',     # Dash symbol
        'Tornado': '🌪️'     # Tornado
    }

    def __init__(self, config: Dict[str, Any], display_manager):
        self.config = config
        self.display_manager = display_manager
        self.weather_config = config.get('weather', {})
        self.location = config.get('location', {})
        self.last_update = 0
        self.weather_data = None
        self.forecast_data = None
        self.hourly_forecast = None
        self.daily_forecast = None
        self.last_draw_time = 0
        # Layout constants
        self.PADDING = 2
        self.ICON_SIZE = {
            'large': 16,
            'medium': 12,
            'small': 8
        }
        self.COLORS = {
            'text': (255, 255, 255),
            'highlight': (255, 200, 0),
            'separator': (64, 64, 64),
            'temp_high': (255, 100, 100),
            'temp_low': (100, 100, 255)
        }
        # Add caching for last drawn states
        self.last_weather_state = None
        self.last_hourly_state = None
        self.last_daily_state = None

    def _fetch_weather(self) -> None:
        """Fetch current weather and forecast data from OpenWeatherMap API."""
        api_key = self.weather_config.get('api_key')
        if not api_key:
            print("No API key configured for weather")
            return

        city = self.location['city']
        state = self.location['state']
        country = self.location['country']
        units = self.weather_config.get('units', 'imperial')

        # First get coordinates using geocoding API
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city},{state},{country}&limit=1&appid={api_key}"
        
        try:
            # Get coordinates
            response = requests.get(geo_url)
            response.raise_for_status()
            geo_data = response.json()
            
            if not geo_data:
                print(f"Could not find coordinates for {city}, {state}")
                return
                
            lat = geo_data[0]['lat']
            lon = geo_data[0]['lon']
            
            # Get current weather and forecast using coordinates
            weather_url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units={units}"
            forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}&units={units}"
            
            # Fetch current weather
            response = requests.get(weather_url)
            response.raise_for_status()
            self.weather_data = response.json()

            # Fetch forecast
            response = requests.get(forecast_url)
            response.raise_for_status()
            self.forecast_data = response.json()

            # Process forecast data
            self._process_forecast_data(self.forecast_data)
            
            self.last_update = time.time()
            print("Weather data updated successfully")
        except Exception as e:
            print(f"Error fetching weather data: {e}")
            self.weather_data = None
            self.forecast_data = None

    def _process_forecast_data(self, forecast_data: Dict[str, Any]) -> None:
        """Process forecast data into hourly and daily forecasts."""
        if not forecast_data:
            return

        # Process hourly forecast (next 6 hours)
        hourly_list = forecast_data.get('list', [])[:6]  # Get next 6 3-hour forecasts
        self.hourly_forecast = []
        
        for hour_data in hourly_list:
            dt = datetime.fromtimestamp(hour_data['dt'])
            temp = round(hour_data['main']['temp'])
            condition = hour_data['weather'][0]['main']
            self.hourly_forecast.append({
                'hour': dt.strftime('%I%p').lstrip('0'),  # Remove leading 0
                'temp': temp,
                'condition': condition
            })

        # Process daily forecast (next 3 days)
        daily_data = {}
        for item in hourly_list:
            date = datetime.fromtimestamp(item['dt']).strftime('%Y-%m-%d')
            if date not in daily_data:
                daily_data[date] = {
                    'temps': [],
                    'conditions': [],
                    'date': datetime.fromtimestamp(item['dt'])
                }
            daily_data[date]['temps'].append(item['main']['temp'])
            daily_data[date]['conditions'].append(item['weather'][0]['main'])

        # Calculate daily summaries
        self.daily_forecast = []
        for date, data in list(daily_data.items())[:3]:  # First 3 days
            temps = data['temps']
            temp_high = round(max(temps))
            temp_low = round(min(temps))
            condition = max(set(data['conditions']), key=data['conditions'].count)
            
            self.daily_forecast.append({
                'date': data['date'].strftime('%a'),  # Day name (Mon, Tue, etc.)
                'date_str': data['date'].strftime('%m/%d'),  # Date (4/8, 4/9, etc.)
                'temp_high': temp_high,
                'temp_low': temp_low,
                'condition': condition
            })

    def get_weather(self) -> Dict[str, Any]:
        """Get current weather data, fetching new data if needed."""
        current_time = time.time()
        if (not self.weather_data or 
            current_time - self.last_update > self.weather_config.get('update_interval', 300)):
            self._fetch_weather()
        return self.weather_data

    def _get_weather_state(self) -> Dict[str, Any]:
        """Get current weather state for comparison."""
        if not self.weather_data:
            return None
        return {
            'temp': round(self.weather_data['main']['temp']),
            'condition': self.weather_data['weather'][0]['main'],
            'humidity': self.weather_data['main']['humidity']
        }

    def _get_hourly_state(self) -> List[Dict[str, Any]]:
        """Get current hourly forecast state for comparison."""
        if not self.hourly_forecast:
            return None
        return [
            {'hour': f['hour'], 'temp': round(f['temp']), 'condition': f['condition']}
            for f in self.hourly_forecast[:3]
        ]

    def _get_daily_state(self) -> List[Dict[str, Any]]:
        """Get current daily forecast state for comparison."""
        if not self.daily_forecast:
            return None
        return [
            {
                'date': f['date'],
                'temp_high': round(f['temp_high']),
                'temp_low': round(f['temp_low']),
                'condition': f['condition']
            }
            for f in self.daily_forecast[:3]
        ]

    def display_weather(self, force_clear: bool = False) -> None:
        """Display current weather information using a static layout."""
        try:
            weather_data = self.get_weather()
            if not weather_data:
                print("No weather data available")
                return

            # Check if state has changed
            current_state = self._get_weather_state()
            if not force_clear and current_state == self.last_weather_state:
                return  # No need to redraw if nothing changed

            # Clear the display once at the start
            self.display_manager.clear()
            
            # Draw temperature (large, centered)
            temp_text = f"{current_state['temp']}°F"
            self.display_manager.draw_text(
                temp_text,
                y=2,
                color=self.COLORS['highlight'],
                small_font=False
            )
            
            # Draw weather icon below temperature
            icon_x = (self.display_manager.matrix.width - self.ICON_SIZE['large']) // 2
            icon_y = self.display_manager.matrix.height // 2 - 4
            self.display_manager.draw_weather_icon(
                current_state['condition'],
                icon_x,
                icon_y,
                size=self.ICON_SIZE['large']
            )
            
            # Draw humidity at bottom
            humidity_text = f"Humidity: {current_state['humidity']}%"
            self.display_manager.draw_text(
                humidity_text,
                y=self.display_manager.matrix.height - 8,
                color=self.COLORS['text'],
                small_font=True
            )
            
            # Update display once after all elements are drawn
            self.display_manager.update_display()
            self.last_weather_state = current_state

        except Exception as e:
            print(f"Error displaying weather: {e}")

    def display_hourly_forecast(self, force_clear: bool = False):
        """Display the next few hours of weather forecast."""
        try:
            if not self.hourly_forecast:
                print("No hourly forecast data available")
                return
            
            # Check if state has changed
            current_state = self._get_hourly_state()
            if not force_clear and current_state == self.last_hourly_state:
                return  # No need to redraw if nothing changed
            
            # Clear once at the start
            self.display_manager.clear()
            
            # Display next 3 hours
            hours_to_show = min(3, len(self.hourly_forecast))
            section_width = self.display_manager.matrix.width // hours_to_show
            
            for i in range(hours_to_show):
                forecast = current_state[i]
                x = i * section_width
                
                # Draw hour
                self.display_manager.draw_text(
                    forecast['hour'],
                    x=x + 2,
                    y=2,
                    color=self.COLORS['text'],
                    small_font=True
                )
                
                # Draw weather icon
                self.display_manager.draw_weather_icon(
                    forecast['condition'],
                    x=x + (section_width - self.ICON_SIZE['medium']) // 2,
                    y=12,
                    size=self.ICON_SIZE['medium']
                )
                
                # Draw temperature
                temp = f"{forecast['temp']}°"
                self.display_manager.draw_text(
                    temp,
                    x=x + (section_width - len(temp) * 4) // 2,
                    y=24,
                    color=self.COLORS['highlight'],
                    small_font=True
                )
            
            # Update display once after all elements are drawn
            self.display_manager.update_display()
            self.last_hourly_state = current_state

        except Exception as e:
            print(f"Error displaying hourly forecast: {e}")

    def display_daily_forecast(self, force_clear: bool = False):
        """Display the 3-day weather forecast."""
        try:
            if not self.daily_forecast:
                print("No daily forecast data available")
                return
            
            # Check if state has changed
            current_state = self._get_daily_state()
            if not force_clear and current_state == self.last_daily_state:
                return  # No need to redraw if nothing changed
            
            # Clear once at the start
            self.display_manager.clear()
            
            # Display 3 days
            days_to_show = min(3, len(self.daily_forecast))
            section_width = self.display_manager.matrix.width // days_to_show
            
            for i in range(days_to_show):
                forecast = current_state[i]
                x = i * section_width
                
                # Draw day name
                self.display_manager.draw_text(
                    forecast['date'].upper(),
                    x=x + 2,
                    y=2,
                    color=self.COLORS['text'],
                    small_font=True
                )
                
                # Draw weather icon
                self.display_manager.draw_weather_icon(
                    forecast['condition'],
                    x=x + (section_width - self.ICON_SIZE['medium']) // 2,
                    y=12,
                    size=self.ICON_SIZE['medium']
                )
                
                # Draw temperature range
                temp = f"{forecast['temp_low']}/{forecast['temp_high']}°"
                self.display_manager.draw_text(
                    temp,
                    x=x + (section_width - len(temp) * 4) // 2,
                    y=24,
                    color=self.COLORS['highlight'],
                    small_font=True
                )
            
            # Update display once after all elements are drawn
            self.display_manager.update_display()
            self.last_daily_state = current_state

        except Exception as e:
            print(f"Error displaying daily forecast: {e}") 