"""Poll an RSS/Atom feed and push new entries to an ntfy topic.

Designed to run from cron/Task Scheduler. Exit codes: 0 = ok, 1 = some
entries failed or the feed could not be read, 2 = bad configuration.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
SEEN_FILE = SCRIPT_DIR / "seen.json"
LEGACY_LAST_SEEN_FILE = SCRIPT_DIR / "last_seen.txt"
LOG_FILE = SCRIPT_DIR / "rss_notifier.log"

load_dotenv(SCRIPT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


CONFIG_ERRORS: list[str] = []


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        CONFIG_ERRORS.append(f"{name} must be an integer, got {value!r}")
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    RSS_URL = os.getenv("RSS_URL", "").strip()
    NTFY_CHANNEL = os.getenv("NTFY_CHANNEL", "").strip()
    NTFY_TOKEN = os.getenv("NTFY_TOKEN", "").strip()
    NTFY_PRIORITY = _env_int("NTFY_PRIORITY", 3)
    MAX_DESCRIPTION_LENGTH = _env_int("MAX_DESCRIPTION_LENGTH", 250)
    REQUEST_TIMEOUT = _env_int("REQUEST_TIMEOUT", 10)
    RETRY_ATTEMPTS = _env_int("RETRY_ATTEMPTS", 3)
    RETRY_DELAY = _env_int("RETRY_DELAY", 2)
    MAX_ENTRIES = _env_int("MAX_ENTRIES", 50)
    SEEN_LIMIT = _env_int("SEEN_LIMIT", 500)
    SEND_ON_FIRST_RUN = _env_bool("SEND_ON_FIRST_RUN", False)


def is_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_config() -> tuple[str, str]:
    """Check config and return (ntfy server base URL, topic)."""
    errors = list(CONFIG_ERRORS)
    if not is_http_url(Config.RSS_URL):
        errors.append("RSS_URL is missing or not an http(s) URL")
    if not is_http_url(Config.NTFY_CHANNEL):
        errors.append("NTFY_CHANNEL is missing or not an http(s) URL")
    if not 1 <= Config.NTFY_PRIORITY <= 5:
        errors.append("NTFY_PRIORITY must be between 1 and 5")
    if Config.SEEN_LIMIT < Config.MAX_ENTRIES:
        errors.append("SEEN_LIMIT must be >= MAX_ENTRIES")
    if errors:
        raise SystemExit("Config error: " + "; ".join(errors))

    # NTFY_CHANNEL is a topic URL (https://ntfy.sh/my-topic). JSON publishing
    # posts to the server root with the topic in the body.
    base, _, topic = Config.NTFY_CHANNEL.rstrip("/").rpartition("/")
    if not topic or not is_http_url(base):
        raise SystemExit("Config error: NTFY_CHANNEL must look like https://ntfy.example.com/topic")
    return base, topic


# ---------------------------------------------------------------- state

def load_seen() -> list[str] | None:
    """Return the list of already-notified entry IDs, or None on first run."""
    if not SEEN_FILE.exists():
        return None
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data]
        logger.error("%s is not a JSON list; ignoring it", SEEN_FILE.name)
    except (OSError, ValueError) as e:
        logger.error("Could not read %s: %s", SEEN_FILE.name, e)
    # A corrupt state file is treated like a first run, so we don't flood.
    return None


def save_seen(seen: list[str]) -> None:
    """Write state atomically, keeping only the most recent SEEN_LIMIT IDs."""
    trimmed = seen[-Config.SEEN_LIMIT:]
    tmp = SEEN_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(trimmed, ensure_ascii=False, indent=0), encoding="utf-8")
    os.replace(tmp, SEEN_FILE)


def load_legacy_last_seen() -> str | None:
    """Last-seen link from older versions of this script (last_seen.txt)."""
    try:
        if LEGACY_LAST_SEEN_FILE.exists():
            return LEGACY_LAST_SEEN_FILE.read_text(encoding="utf-8").strip() or None
    except OSError as e:
        logger.warning("Could not read %s: %s", LEGACY_LAST_SEEN_FILE.name, e)
    return None


# ---------------------------------------------------------------- content

def entry_id(entry) -> str:
    return entry.get("id") or entry.get("link") or entry.get("title") or ""


def clean_text(raw: str) -> str:
    text = re.sub(r"<[^>]*>", " ", raw or "")
    text = html.unescape(text)
    return " ".join(text.split())


def truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def find_image_url(entry) -> str:
    candidates = []
    for media in entry.get("media_content", []) + entry.get("media_thumbnail", []):
        candidates.append(media.get("url", ""))
    for enc in entry.get("enclosures", []):
        if str(enc.get("type", "")).startswith("image/"):
            candidates.append(enc.get("href", ""))
    html_body = entry.get("description", "") or entry.get("summary", "")
    match = re.search(r"""<img[^>]+src=["']([^"']+)["']""", html_body, re.IGNORECASE)
    if match:
        candidates.append(html.unescape(match.group(1)))
    return next((url for url in candidates if is_http_url(url)), "")


def build_payload(entry, topic: str) -> dict:
    title = clean_text(entry.get("title", "")) or "(untitled)"
    link = (entry.get("link") or "").strip()
    description = truncate(
        clean_text(entry.get("description", "") or entry.get("summary", "")),
        Config.MAX_DESCRIPTION_LENGTH,
    )
    tags = ", ".join(t.get("term", "") for t in entry.get("tags", []) if t.get("term"))

    parts = [description] if description else []
    if link:
        parts.append(f"Read more: {link}")
    if tags:
        parts.append(f"Tags: {tags}")

    payload = {
        "topic": topic,
        "title": title,
        "message": "\n\n".join(parts) or title,
        "priority": Config.NTFY_PRIORITY,
        "tags": ["rss"],
    }
    if is_http_url(link):
        payload["click"] = link
    image_url = find_image_url(entry)
    if image_url:
        payload["attach"] = image_url
    return payload


# ---------------------------------------------------------------- network

def fetch_feed(url: str):
    response = requests.get(url, timeout=Config.REQUEST_TIMEOUT)
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    if feed.bozo:
        # feedparser flags minor issues (e.g. wrong declared encoding) even
        # when entries parsed fine, so only give up if nothing came through.
        logger.warning("Feed parser warning: %s", feed.bozo_exception)
        if not feed.entries:
            raise ValueError(f"Feed could not be parsed: {feed.bozo_exception}")
    return feed


def send_notification(base_url: str, payload: dict) -> bool:
    headers = {}
    if Config.NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {Config.NTFY_TOKEN}"
    for attempt in range(1, Config.RETRY_ATTEMPTS + 1):
        try:
            response = requests.post(
                base_url, json=payload, headers=headers, timeout=Config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            logger.info("Sent: %s", payload["title"])
            return True
        except requests.RequestException as e:
            logger.warning("Send attempt %d/%d failed for %r: %s",
                           attempt, Config.RETRY_ATTEMPTS, payload["title"], e)
            if attempt < Config.RETRY_ATTEMPTS:
                time.sleep(Config.RETRY_DELAY)
    return False


# ---------------------------------------------------------------- main

def run() -> int:
    base_url, topic = validate_config()

    try:
        feed = fetch_feed(Config.RSS_URL)
    except (requests.RequestException, ValueError) as e:
        logger.error("Could not fetch feed: %s", e)
        return 1

    # Feeds list newest first; send oldest first so notifications arrive in order.
    entries = [e for e in feed.entries[:Config.MAX_ENTRIES] if entry_id(e)]
    entries.reverse()

    seen = load_seen()
    if seen is None:
        legacy_link = load_legacy_last_seen()
        links = [e.get("link") for e in entries]
        if legacy_link and legacy_link in links:
            # Upgrade path: everything up to and including the old last-seen
            # link counts as already sent.
            seen = [entry_id(e) for e in entries[:links.index(legacy_link) + 1]]
            logger.info("Migrated from %s (%d entries marked as seen)",
                        LEGACY_LAST_SEEN_FILE.name, len(seen))
        elif not Config.SEND_ON_FIRST_RUN:
            save_seen([entry_id(e) for e in entries])
            logger.info("First run: marked %d current entries as seen without sending "
                        "(set SEND_ON_FIRST_RUN=true to send them)", len(entries))
            return 0
        else:
            seen = []

    seen_set = set(seen)
    new_entries = [e for e in entries if entry_id(e) not in seen_set]
    if not new_entries:
        logger.info("No new entries")
        save_seen(seen)
        return 0

    failures = 0
    for entry in new_entries:
        try:
            ok = send_notification(base_url, build_payload(entry, topic))
        except Exception:  # one malformed entry must not block the rest
            logger.exception("Could not process entry %r", entry_id(entry))
            ok = False
        if ok:
            seen.append(entry_id(entry))
            seen_set.add(entry_id(entry))
            save_seen(seen)  # save after each send so a crash can't cause repeats
        else:
            failures += 1  # left unseen, retried on the next run
        time.sleep(1)  # be polite to the ntfy server

    logger.info("Processed %d new entries (%d failed)", len(new_entries), failures)
    return 1 if failures else 0


def main() -> int:
    logger.info("Starting RSS notification run")
    try:
        code = run()
    except SystemExit as e:
        logger.error("%s", e)
        code = 2
    except Exception:
        logger.exception("Unexpected error")
        code = 1
    logger.info("Run finished (exit code %d)", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
