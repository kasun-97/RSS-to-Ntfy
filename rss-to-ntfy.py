import feedparser
import requests
import os
import re
import unidecode

# RSS feed URL
RSS_URL = "https://freshrss.example.com/api/query.php?user=user&t=4oaxDvIpI78Y7xzSxGzS71&f=rss"

# ntfy channel URL
NTFY_CHANNEL = "https://ntfy.example.com/4EKIsD7SHxFD9IF2"

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# File to store the last seen post link
LAST_SEEN_FILE = os.path.join(script_dir, "last_seen.txt")

def load_last_seen():
    """Load the last seen post link from file."""
    if os.path.exists(LAST_SEEN_FILE):
        with open(LAST_SEEN_FILE, "r") as file:
            return file.read().strip()
    return None

def save_last_seen(last_link):
    """Save the last seen post link to file."""
    with open(LAST_SEEN_FILE, "w") as file:
        file.write(last_link)

def fetch_image_url(entry):
    """Extract image URL from entry, if available."""
    if hasattr(entry, 'media_content') and entry.media_content:
        return entry.media_content[0].get('url', "")
    elif hasattr(entry, 'image'):
        return entry.image.href
    elif hasattr(entry, 'description'):
        match = re.search(r'<img src="(.*?)"', entry.description)
        if match:
            return match.group(1)
    return ""

def truncate_description(description, max_length=250):
    """Truncate the description to the specified max length."""
    # Remove HTML tags
    description = re.sub(r'<.*?>', '', description)
    # Return the first `max_length` characters
    return description[:max_length].strip() + '...' if len(description) > max_length else description.strip()

def send_notification(title, description, link, tags, image_url=None):
    """Send a notification to the ntfy channel."""
    # Sanitize title for headers
    sanitized_title = unidecode.unidecode(title).strip()
    sanitized_title = re.sub(r'[\r\n]+', ' ', sanitized_title)  # Replace newlines with space
    sanitized_title = re.sub(r'[<>]', '', sanitized_title)  # Remove any angle brackets

    # Truncate the description
    truncated_description = truncate_description(description)

    # Remove trailing slash from the link if present
    clean_link = link.rstrip('/')

    # Format the message with title, description, link, and tags
    message = f"{truncated_description}\n\nRead more: {clean_link}\n\nTags: {tags}"
    
    headers = {
        "Title": sanitized_title,  # Use sanitized title for the notification heading
        "Click": clean_link        # Make the link clickable
    }
    if image_url:
        headers["Attach"] = image_url  # Attach image if available
    
    # Send the notification with UTF-8 encoding
    try:
        response = requests.post(
            NTFY_CHANNEL,
            headers=headers,
            data=message.encode('utf-8')
        )
        response.raise_for_status()  # Raise exception for HTTP errors
    except requests.RequestException as e:
        print(f"Error sending notification: {e}")


def main():
    # Load the last seen post link
    last_seen_link = load_last_seen()
    
    # Parse the RSS feed
    feed = feedparser.parse(RSS_URL)
    
    # Track new entries to update last_seen_link only once
    new_entries = []
    
    # Check for new posts
    for entry in feed.entries:
        post_link = entry.link
        if post_link == last_seen_link:
            break  # Stop processing when we reach the last seen post
        new_entries.append(entry)  # Collect new entries

    # Send notifications for new entries in reverse order to keep sequence
    for entry in reversed(new_entries):
        tags = ', '.join(tag.term for tag in entry.tags) if hasattr(entry, 'tags') else "No tags available"
        image_url = fetch_image_url(entry)
        description = entry.description
        send_notification(entry.title, description, entry.link, tags, image_url)

    # Update the last seen link if there were new entries
    if new_entries:
        save_last_seen(new_entries[0].link)

if __name__ == "__main__":
    main()
