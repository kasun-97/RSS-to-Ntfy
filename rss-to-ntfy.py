import feedparser
import requests
import os
import re
import unidecode
import logging
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from dotenv import load_dotenv
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rss_notifier.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
class Config:
    RSS_URL = os.getenv('RSS_URL', 'https://freshrss.example.com/api/query.php')
    NTFY_CHANNEL = os.getenv('NTFY_CHANNEL', 'https://ntfy.example.com/channel')
    MAX_DESCRIPTION_LENGTH = 250
    REQUEST_TIMEOUT = 10
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2
    MAX_ENTRIES = 50

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
LAST_SEEN_FILE = os.path.join(script_dir, "last_seen.txt")

class URLValidator:
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """Validate if the provided URL is properly formatted."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception as e:
            logger.error(f"URL validation error: {e}")
            return False

    @staticmethod
    def validate_config_urls():
        """Validate configuration URLs."""
        if not URLValidator.is_valid_url(Config.RSS_URL):
            raise ValueError("Invalid RSS URL in configuration")
        if not URLValidator.is_valid_url(Config.NTFY_CHANNEL):
            raise ValueError("Invalid NTFY channel URL in configuration")

class FileHandler:
    @staticmethod
    def load_last_seen() -> Optional[str]:
        """Load the last seen post link from file."""
        try:
            if os.path.exists(LAST_SEEN_FILE):
                with open(LAST_SEEN_FILE, "r", encoding='utf-8') as file:
                    return file.read().strip()
        except Exception as e:
            logger.error(f"Error loading last seen file: {e}")
        return None

    @staticmethod
    def save_last_seen(last_link: str) -> None:
        """Save the last seen post link to file."""
        try:
            with open(LAST_SEEN_FILE, "w", encoding='utf-8') as file:
                file.write(last_link)
        except Exception as e:
            logger.error(f"Error saving last seen file: {e}")

class ContentProcessor:
    @staticmethod
    def fetch_image_url(entry: Dict[str, Any]) -> str:
        """Extract image URL from entry, if available."""
        try:
            if hasattr(entry, 'media_content') and entry.media_content:
                return entry.media_content[0].get('url', "")
            elif hasattr(entry, 'image'):
                return entry.image.href
            elif hasattr(entry, 'description'):
                match = re.search(r'<img src="(.*?)"', entry.description)
                if match:
                    return match.group(1)
        except Exception as e:
            logger.error(f"Error fetching image URL: {e}")
        return ""

    @staticmethod
    def truncate_description(description: str, max_length: int = Config.MAX_DESCRIPTION_LENGTH) -> str:
        """Truncate and clean the description."""
        try:
            # Remove HTML tags
            clean_desc = re.sub(r'<.*?>', '', description)
            # Remove extra whitespace
            clean_desc = ' '.join(clean_desc.split())
            if len(clean_desc) > max_length:
                return clean_desc[:max_length].strip() + '...'
            return clean_desc.strip()
        except Exception as e:
            logger.error(f"Error processing description: {e}")
            return "Description processing error"

class NotificationSender:
    @staticmethod
    def send_with_retry(title: str, description: str, link: str, tags: str, image_url: Optional[str] = None) -> bool:
        """Send notification with retry mechanism."""
        for attempt in range(Config.RETRY_ATTEMPTS):
            try:
                NotificationSender._send_notification(title, description, link, tags, image_url)
                return True
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < Config.RETRY_ATTEMPTS - 1:
                    time.sleep(Config.RETRY_DELAY)
        logger.error("All retry attempts failed")
        return False

    @staticmethod
    def _send_notification(title: str, description: str, link: str, tags: str, image_url: Optional[str]) -> None:
        """Send a notification to the ntfy channel."""
        sanitized_title = unidecode.unidecode(title).strip()
        sanitized_title = re.sub(r'[\r\n]+', ' ', sanitized_title)
        sanitized_title = re.sub(r'[<>]', '', sanitized_title)

        clean_link = link.rstrip('/')
        message = f"{description}\n\nRead more: {clean_link}\n\nTags: {tags}"
        
        headers = {
            "Title": sanitized_title,
            "Click": clean_link,
            "X-Priority": "5",
            "Tags": "rss"
        }
        
        if image_url and URLValidator.is_valid_url(image_url):
            headers["Attach"] = image_url

        response = requests.post(
            Config.NTFY_CHANNEL,
            headers=headers,
            data=message.encode('utf-8'),
            timeout=Config.REQUEST_TIMEOUT
        )
        response.raise_for_status()
        logger.info(f"Notification sent successfully: {sanitized_title}")

class RSSProcessor:
    def __init__(self):
        self.last_seen_link = FileHandler.load_last_seen()

    def process_feed(self) -> None:
        """Process the RSS feed and send notifications."""
        try:
            URLValidator.validate_config_urls()
            feed = feedparser.parse(Config.RSS_URL)
            
            if feed.bozo:
                logger.error(f"Feed parsing error: {feed.bozo_exception}")
                return

            new_entries = []
            for entry in feed.entries[:Config.MAX_ENTRIES]:
                if entry.link == self.last_seen_link:
                    break
                new_entries.append(entry)

            if not new_entries:
                logger.info("No new entries found")
                return

            for entry in reversed(new_entries):
                tags = ', '.join(tag.term for tag in entry.tags) if hasattr(entry, 'tags') else "No tags"
                image_url = ContentProcessor.fetch_image_url(entry)
                description = ContentProcessor.truncate_description(entry.description)
                
                NotificationSender.send_with_retry(
                    entry.title,
                    description,
                    entry.link,
                    tags,
                    image_url
                )
                time.sleep(1)  # Rate limiting

            if new_entries:
                FileHandler.save_last_seen(new_entries[0].link)
                logger.info(f"Processed {len(new_entries)} new entries")

        except Exception as e:
            logger.error(f"Error processing feed: {e}")

def main():
    """Main execution function."""
    logger.info("Starting RSS notification service")
    try:
        processor = RSSProcessor()
        processor.process_feed()
    except Exception as e:
        logger.error(f"Main execution error: {e}")
    logger.info("RSS notification service completed")

if __name__ == "__main__":
    main()
