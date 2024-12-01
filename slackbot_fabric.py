import os
import re
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import subprocess
import logging
import time
import json
from datetime import datetime

# Set up detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize the Slack app with your bot token
app = App(token=os.environ["SLACK_BOT_TOKEN"])

# Create a persistent directory for files
WORK_DIR = os.path.join(os.getcwd(), "youtube_transcripts")
os.makedirs(WORK_DIR, exist_ok=True)
logger.info(f"Work directory created/verified at: {WORK_DIR}")

def extract_video_id(url):
    """Extract YouTube video ID from URL."""
    patterns = [
        r'(?:v=|\/)([\w-]{11})',
        r'(?:youtu.be\/)([\w-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def process_youtube_url(url):
    """Process YouTube URL to extract transcript and wisdom."""
    start_time = time.time()
    video_id = extract_video_id(url)
    
    if not video_id:
        logger.error(f"Failed to extract video ID from URL: {url}")
        return "Invalid YouTube URL format"
    
    logger.info(f"Successfully extracted video ID: {video_id}")
    
    try:
        # Create timestamped directory for this run
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = os.path.join(WORK_DIR, f"{video_id}_{timestamp}")
        os.makedirs(run_dir, exist_ok=True)
        logger.info(f"Created run directory: {run_dir}")
        
        # Get transcript
        transcript_path = os.path.join(run_dir, f"{video_id}.txt")
        transcript_command = ["yt", "--transcript", url]
        
        logger.info("Starting transcript extraction...")
        logger.info(f"Executing command: {' '.join(transcript_command)}")
        
        transcript_start = time.time()
        transcript_process = subprocess.run(
            transcript_command, 
            check=True, 
            stdout=open(transcript_path, 'w'),
            stderr=subprocess.PIPE
        )
        transcript_time = time.time() - transcript_start
        
        # Log transcript file details
        if os.path.exists(transcript_path):
            file_size = os.path.getsize(transcript_path)
            logger.info(f"Transcript file created: {transcript_path}")
            logger.info(f"Transcript file size: {file_size} bytes")
            logger.info(f"Transcript extraction took: {transcript_time:.2f} seconds")
        else:
            logger.error("Transcript file was not created!")
        
        # Extract wisdom using fabric
        wisdom_path = os.path.join(run_dir, f"{video_id}_wisdom.txt")
        fabric_command = f"cat {transcript_path} | fabric --pattern extract_wisdom"
        logger.info("Starting wisdom extraction...")
        logger.info(f"Executing command: {fabric_command}")
        
        wisdom_start = time.time()
        result = subprocess.run(
            fabric_command,
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        wisdom_time = time.time() - wisdom_start
        
        # Save wisdom output to file
        with open(wisdom_path, 'w') as f:
            f.write(result.stdout)
        
        # Log wisdom extraction details
        logger.info(f"Wisdom extraction took: {wisdom_time:.2f} seconds")
        logger.info(f"Wisdom output saved to: {wisdom_path}")
        logger.info(f"Wisdom output length: {len(result.stdout)} characters")
        
        total_time = time.time() - start_time
        logger.info(f"Total processing time: {total_time:.2f} seconds")
        
        return result.stdout.strip()
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed with return code {e.returncode}")
        logger.error(f"Command output: {e.output}")
        logger.error(f"Command stderr: {e.stderr}")
        return f"Error processing video: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return f"Unexpected error: {str(e)}"

def process_message_text(text, channel, client, user_id=None):
    """Process message text for YouTube URL extraction command."""
    if text and text.startswith("extract_wisdom"):
        # Log message details
        logger.info(f"""
Message Details:
- Channel: {channel}
- User: {user_id if user_id else 'Unknown'}
- Full message: {text}
- Timestamp: {datetime.now().isoformat()}
""")
        
        # Updated pattern to match URLs wrapped in angle brackets
        match = re.search(r"extract_wisdom\s+<(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/.+?)>", text)
        if match:
            url = match.group(1)  # Extract URL from within brackets
            logger.info(f"Processing URL: {url}")
            
            # Send initial message
            client.chat_postMessage(
                channel=channel,
                text="Processing your request... :hourglass_flowing_sand:"
            )
            
            # Process URL and time it
            start_time = time.time()
            result = process_youtube_url(url)
            process_time = time.time() - start_time
            
            # Log processing completion
            logger.info(f"URL processing completed in {process_time:.2f} seconds")
            
            # Send result
            client.chat_postMessage(
                channel=channel,
                text=f"Here's the extracted wisdom:\n```\n{result}\n```"
            )
        else:
            logger.warning(f"Invalid URL format received: {text}")
            client.chat_postMessage(
                channel=channel,
                text="Please provide a YouTube URL wrapped in angle brackets, like this:\nextract_wisdom <https://youtube.com/...>"
            )

@app.event("message")
def handle_message_events(body, logger):
    """Handle only new messages."""
    event = body["event"]
    
    # Enhanced event logging
    logger.info("New message event received:")
    logger.info(json.dumps(event, indent=2))
    
    # Only process new messages (no subtype means it's a new message)
    if "subtype" not in event and "text" in event:
        logger.info(f"Processing new message from user {event.get('user', 'Unknown')}")
        process_message_text(
            event["text"],
            event["channel"],
            app.client,
            event.get("user")
        )

@app.error
def custom_error_handler(error, body, logger):
    """Handle any errors that occur."""
    logger.error("Error occurred in Slack app:", exc_info=True)
    logger.error(f"Event body: {json.dumps(body, indent=2)}")

def main():
    """Main function to start the bot."""
    try:
        # Log environment info
        logger.info(f"Python version: {os.sys.version}")
        logger.info(f"Current working directory: {os.getcwd()}")
        logger.info(f"Working directory for transcripts: {WORK_DIR}")
        logger.info("Starting Slack bot...")
        
        handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
        logger.info("⚡️ Bolt app is running!")
        handler.start()
    except Exception as e:
        logger.error("Failed to start bot:", exc_info=True)
        raise

if __name__ == "__main__":
    main()
