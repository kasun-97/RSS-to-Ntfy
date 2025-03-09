# RSS-to-Ntfy

# Overview
A simple python based script that monitors RSS feeds and sends new posts as notifications through Ntfy. 

## 🌟 Features
- 🔄 Real-time RSS feed monitoring
- 📱 Push notifications via Ntfy
- 🖼️ Image attachment support
- 🏷️ Tag handling
- 📝 Smart description truncation
- 🔁 Retry mechanism for failed notifications
- 📋 Last seen post tracking
- 📊 Comprehensive logging


## Requirements
- Python 3.7+
- RSS feed URL (e.g.: FreshRSS instance)
- Ntfy channel

# Installation
1. Clone the repository
```
git clone https://github.com/kasun-97/RSS-to-Ntfy
cd RSS-to-Ntfy
```

2. Create a virtual environment (optional but recommended)
```
python3 -m venv venv
source venv/bin/activate # On Windows: venv\Scripts\activate
```

3. Install required packages
```
pip install -r requirements.txt
```

## Usage
1. Configure your environment variables in the `.env` file 
```
RSS_URL=https://your-freshrss-instance/api/feed.php
NTFY_CHANNEL=https://ntfy.sh/your-channel
```

2. Run the script
```
python3 ./rss-to-ntfy.py
```

3. (Optional) Set up as a scheduled task
   - If you are not using a virtual environment:
     ```
     */5 * * * * /path/to/python /path/to/rss-to-ntfy.py
     ```

    - If you are using a virtual environment, create a shell script (e.g., `run_rss_notifier.sh`):
      
      ```
      #!/bin/bash 
      
      # Set path to your project
      PROJECT_DIR="/path/to/your/project" 
      
      # Activate virtual environment and run script
      source $PROJECT_DIR/venv/bin/activate 
      python3 $PROJECT_DIR/rss-to-ntfy.py
      
      # Deactivate virtual environment
      deactivate
      ```
      
      Make it executable:
      
      ```
      chmod +x run_rss_notifier.sh
      ```
      
      Add to crontab:
      
      ```
      # Run every 5 minutes 
      */5 * * * * /path/to/your/project/run_rss_notifier.sh >> /path/to/your/project/cron.log 2>&1
      ```

## Configuration Options
The script can be configured through environment variables or by modifying the `Config` class:

| Parameter | Description | Default |
|-----------|-------------|---------|
| RSS_URL | Your RSS feed URL | None |
| NTFY_CHANNEL | Your Ntfy channel URL | None |
| MAX_DESCRIPTION_LENGTH | Maximum length for truncated descriptions | 250 |
| REQUEST_TIMEOUT | Timeout for HTTP requests (seconds) | 10 |
| RETRY_ATTEMPTS | Number of retry attempts for failed notifications | 3 |
| RETRY_DELAY | Delay between retry attempts (seconds) | 2 |
| MAX_ENTRIES | Maximum number of entries to process at once | 50 |


## Logging
The script generates logs in `rss_notifier.log` with the following information:
- Script start/stop times
- Successful notifications
- Error messages
- Processing statistics

## Acknowledgments

- [FreshRSS](https://freshrss.org/) for RSS feed management
- [Ntfy](https://ntfy.sh/) for notification delivery
- All contributors and users of this project
