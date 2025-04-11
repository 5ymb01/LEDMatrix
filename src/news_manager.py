import time
import logging
import requests
import json
import random
from typing import Dict, Any, List, Tuple
from datetime import datetime
import os
import urllib.parse
import re
from src.config_manager import ConfigManager
from PIL import Image, ImageDraw

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NewsManager:
    def __init__(self, config: Dict[str, Any], display_manager):
        self.config = config
        self.config_manager = ConfigManager()
        self.display_manager = display_manager
        self.stocks_config = config.get('stocks', {})
        self.news_config = config.get('news', {})
        self.last_update = 0
        self.news_data = {}
        self.current_news_index = 0
        self.scroll_position = 0
        
        # Get scroll settings from config with faster defaults
        self.scroll_speed = self.news_config.get('scroll_speed', 1)
        self.scroll_delay = self.news_config.get('scroll_delay', 0.001)  # Default to 1ms instead of 50ms
        
        # Log the actual values being used
        logger.info(f"Scroll settings - Speed: {self.scroll_speed} pixels/frame, Delay: {self.scroll_delay*1000:.2f}ms")
        
        # Initialize frame rate tracking
        self.frame_count = 0
        self.last_frame_time = time.time()
        self.last_fps_log_time = time.time()
        self.frame_times = []  # Keep track of recent frame times for average FPS
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        # Initialize with first update
        self.update_news_data()
        
    def _fetch_news_for_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """Fetch news headlines for a stock symbol."""
        try:
            # Using Yahoo Finance API to get news
            encoded_symbol = urllib.parse.quote(symbol)
            url = f"https://query1.finance.yahoo.com/v1/finance/search?q={encoded_symbol}&lang=en-US&region=US&quotesCount=0&newsCount={self.news_config.get('max_headlines_per_symbol', 5)}"
            
            response = requests.get(url, headers=self.headers, timeout=5)
            if response.status_code != 200:
                logger.error(f"Failed to fetch news for {symbol}: HTTP {response.status_code}")
                return []
                
            data = response.json()
            news_items = data.get('news', [])
            
            # Process and format news items
            formatted_news = []
            for item in news_items:
                formatted_news.append({
                    "title": item.get('title', ''),
                    "publisher": item.get('publisher', ''),
                    "link": item.get('link', ''),
                    "published": item.get('providerPublishTime', 0)
                })
                
            logger.info(f"Fetched {len(formatted_news)} news items for {symbol}")
            return formatted_news
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching news for {symbol}: {e}")
            return []
        except (ValueError, IndexError, KeyError) as e:
            logger.error(f"Error parsing news data for {symbol}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching news for {symbol}: {e}")
            return []
            
    def update_news_data(self):
        """Update news data for all configured stock symbols."""
        current_time = time.time()
        update_interval = self.news_config.get('update_interval', 300)  # Default to 5 minutes
        
        # If not enough time has passed, keep using existing data
        if current_time - self.last_update < update_interval:
            return
            
        # Get symbols from config
        symbols = self.stocks_config.get('symbols', [])
        if not symbols:
            logger.warning("No stock symbols configured for news")
            return
            
        # Create temporary storage for new data
        new_data = {}
        success = False
        
        for symbol in symbols:
            # Add a small delay between requests to avoid rate limiting
            time.sleep(random.uniform(0.1, 0.3))
            news_items = self._fetch_news_for_symbol(symbol)
            if news_items:
                new_data[symbol] = news_items
                success = True
                
        if success:
            # Only update the displayed data when we have new data
            self.news_data = new_data
            self.last_update = current_time
            self.current_news_index = 0
            self.scroll_position = 0
            logger.info(f"Updated news data for {len(new_data)} symbols")
        else:
            logger.error("Failed to fetch news for any configured stocks")
            
    def _create_text_image(self, text: str, color: Tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
        """Create an image containing the text for efficient scrolling."""
        # Get text dimensions
        bbox = self.display_manager.draw.textbbox((0, 0), text, font=self.display_manager.small_font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Create a new image with the text
        text_image = Image.new('RGB', (text_width, self.display_manager.matrix.height), (0, 0, 0))
        text_draw = ImageDraw.Draw(text_image)
        
        # Draw the text centered vertically
        y = (self.display_manager.matrix.height - text_height) // 2
        text_draw.text((0, y), text, font=self.display_manager.small_font, fill=color)
        
        return text_image
            
    def _log_frame_rate(self):
        """Log frame rate statistics."""
        current_time = time.time()
        
        # Calculate instantaneous frame time
        frame_time = current_time - self.last_frame_time
        self.frame_times.append(frame_time)
        
        # Keep only last 100 frames for average
        if len(self.frame_times) > 100:
            self.frame_times.pop(0)
        
        # Log FPS every second
        if current_time - self.last_fps_log_time >= 1.0:
            avg_frame_time = sum(self.frame_times) / len(self.frame_times)
            avg_fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
            instant_fps = 1.0 / frame_time if frame_time > 0 else 0
            
            logger.info(f"Frame stats - Avg FPS: {avg_fps:.1f}, Current FPS: {instant_fps:.1f}, Frame time: {frame_time*1000:.2f}ms")
            self.last_fps_log_time = current_time
            self.frame_count = 0
        
        self.last_frame_time = current_time
        self.frame_count += 1

    def display_news(self):
        """Display news headlines by scrolling them across the screen."""
        if not self.news_config.get('enabled', False):
            return
            
        # Start update in background if needed
        if time.time() - self.last_update >= self.news_config.get('update_interval', 300):
            self.update_news_data()
            
        if not self.news_data:
            logger.warning("No news data available to display")
            return
            
        # Get all news items from all symbols
        all_news = []
        for symbol, news_items in self.news_data.items():
            for item in news_items:
                all_news.append({
                    "symbol": symbol,
                    "title": item["title"],
                    "publisher": item["publisher"]
                })
                
        if not all_news:
            return
            
        # Get the current news item to display
        current_news = all_news[self.current_news_index]
        next_news = all_news[(self.current_news_index + 1) % len(all_news)]
        
        # Format the news text with proper spacing and separator
        separator = "   -   "  # Visual separator between news items
        current_text = f"{current_news['symbol']}: {current_news['title']}"
        next_text = f"{next_news['symbol']}: {next_news['title']}"
        news_text = f"{current_text}{separator}{next_text}"
        
        # Create a text image for efficient scrolling (only if needed)
        if not hasattr(self, '_current_text_image') or self._current_text != news_text:
            self._current_text_image = self._create_text_image(news_text)
            self._current_text = news_text
            text_width = self._current_text_image.width
            self._text_width = text_width
        else:
            text_width = self._text_width
        
        # Calculate the visible portion of the text
        visible_width = min(self.display_manager.matrix.width, text_width)
        
        # Create a new image for the current frame
        frame_image = Image.new('RGB', (self.display_manager.matrix.width, self.display_manager.matrix.height), (0, 0, 0))
        
        # Calculate the source and destination regions for the visible portion
        src_x = self.scroll_position % text_width  # Use modulo to wrap around smoothly
        src_width = min(visible_width, text_width - src_x)
        
        # Copy the visible portion of the text to the frame
        if src_width > 0:
            src_region = self._current_text_image.crop((src_x, 0, src_x + src_width, self.display_manager.matrix.height))
            frame_image.paste(src_region, (0, 0))
        
        # If we need to wrap around to the beginning of the text
        if src_x + src_width >= text_width:
            remaining_width = self.display_manager.matrix.width - src_width
            if remaining_width > 0:
                wrap_src_width = min(remaining_width, text_width)
                wrap_region = self._current_text_image.crop((0, 0, wrap_src_width, self.display_manager.matrix.height))
                frame_image.paste(wrap_region, (src_width, 0))
        
        # Update the display with the new frame
        self.display_manager.image = frame_image
        self.display_manager.draw = ImageDraw.Draw(frame_image)
        self.display_manager.update_display()
        
        # Log frame rate
        self._log_frame_rate()
        
        # Update scroll position
        self.scroll_position += self.scroll_speed
        
        # If we've scrolled past the current text, move to the next news item
        if self.scroll_position >= text_width:
            self.scroll_position = 0
            self.current_news_index = (self.current_news_index + 1) % len(all_news)
        
        # Add a small delay to control scroll speed
        if self.scroll_delay > 0:
            time.sleep(self.scroll_delay)
        
        return True 