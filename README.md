# RSS-to-Ntfy

A small Python script that checks an RSS/Atom feed and sends each new post as a push notification through [ntfy](https://ntfy.sh/). It is meant to run on a schedule (cron or Windows Task Scheduler), for example every 5 minutes.

## Features
- 📱 Push notifications via ntfy, with click-through link, image attachment and feed tags
- 🌐 Full Unicode support in titles and links (Sinhala, Tamil, etc.)
- 📋 Remembers which posts were already sent, so nothing is sent twice or skipped
- 🔕 No flood on first run: existing posts are marked as seen, not sent
- 🔁 Retries failed sends; failed posts are retried on the next run
- 🔐 Optional ntfy access token for protected topics
- 📊 Rotating log file and meaningful exit codes for monitoring

## Requirements
- Python 3.8+
- An RSS/Atom feed URL (e.g. a FreshRSS instance)
- An ntfy topic (ntfy.sh or self-hosted)

## Installation
1. Clone the repository
   ```
   git clone https://github.com/kasun-97/RSS-to-Ntfy
   cd RSS-to-Ntfy
   ```

2. Create a virtual environment (optional but recommended)
   ```
   python3 -m venv venv
   source venv/bin/activate    # On Windows: venv\Scripts\activate
   ```

3. Install required packages
   ```
   pip install -r requirements.txt
   ```

## Usage
1. Copy `.env.example` to `.env` and set at least:
   ```
   RSS_URL=https://your-freshrss-instance/api/query.php
   NTFY_CHANNEL=https://ntfy.sh/your-channel
   ```
   `.env` is git-ignored, so your feed token and topic stay out of the repo.

2. Run the script
   ```
   python3 ./rss-to-ntfy.py
   ```
   The first run only records the posts currently in the feed. From then on, each new post is sent once. Set `SEND_ON_FIRST_RUN=true` to send the current posts too.

3. (Optional) Schedule it
   - With cron, using the virtual environment's Python directly (no activation script needed):
     ```
     */5 * * * * /path/to/RSS-to-Ntfy/venv/bin/python /path/to/RSS-to-Ntfy/rss-to-ntfy.py
     ```
   - On Windows, create a Task Scheduler task that runs `venv\Scripts\python.exe` with the script path as the argument, repeating every 5 minutes.

   The script reads `.env` and writes its state and log next to itself, so it works regardless of the working directory.

## Configuration
All settings are read from environment variables or `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `RSS_URL` | Feed URL (**required**) | — |
| `NTFY_CHANNEL` | ntfy topic URL, e.g. `https://ntfy.sh/my-topic` (**required**) | — |
| `NTFY_TOKEN` | ntfy access token for protected topics | none |
| `NTFY_PRIORITY` | Notification priority, 1 (min) to 5 (urgent) | 3 |
| `SEND_ON_FIRST_RUN` | Send posts already in the feed on the first run | false |
| `MAX_DESCRIPTION_LENGTH` | Maximum characters of the post description | 250 |
| `REQUEST_TIMEOUT` | Timeout for feed and ntfy requests (seconds) | 10 |
| `RETRY_ATTEMPTS` | Send attempts per notification | 3 |
| `RETRY_DELAY` | Delay between attempts (seconds) | 2 |
| `MAX_ENTRIES` | Maximum feed entries checked per run | 50 |
| `SEEN_LIMIT` | Number of sent post IDs remembered | 500 |

The script stops with an error if `RSS_URL` or `NTFY_CHANNEL` is missing or invalid.

## Files and exit codes
| File | Purpose |
|------|---------|
| `seen.json` | IDs of posts already sent. Delete it to start fresh. |
| `rss_notifier.log` | Log, rotated at 1 MB (3 backups kept) |

| Exit code | Meaning |
|-----------|---------|
| 0 | Success (including "no new posts") |
| 1 | Feed could not be fetched, or some notifications failed |
| 2 | Configuration error |

Upgrading from an older version: an existing `last_seen.txt` is read once to work out which posts were already sent, so the upgrade doesn't resend old posts.

## Acknowledgments
- [FreshRSS](https://freshrss.org/) for RSS feed management
- [ntfy](https://ntfy.sh/) for notification delivery

## License
[MIT](LICENSE)
