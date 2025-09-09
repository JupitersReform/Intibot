import asyncio
import argparse
import json
import os
import praw
from buttplug import Client, WebsocketConnector, ProtocolSpec

CONFIG_FILE = "config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError("Missing config.json. Please create it.")
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

config = load_config()

# ====== CONFIGURATION ======
CACHE_FILE = "settings_cache.json"
VIBRATION_DURATION = 2.0
BUTTPLUG_SERVER_URL = "ws://localhost:12345"

# ====== ARGUMENT PARSING ======
parser = argparse.ArgumentParser(description="Run the Reddit Buttplug Bot.")

parser.add_argument('-p', '--id', type=str,
                    help="Reddit post ID (e.g., 'gxvdih')")

parser.add_argument('-m', '--minimum', type=float,
                    help="Minimum vibration intensity (0.0–1.0)")

parser.add_argument('-u', '--max-upvotes', type=int,
                    help="Upvote count where intensity hits 1.0")

parser.add_argument('-r', '--reset', action='store_true',
                    help="Reset cached settings to default")

parser.add_argument('-k', '--keywords', type=str,
                    help="Comma-separated keyword triggers (e.g., 'knot,choke,gock')")

parser.add_argument('-x', '--multiplier', type=float,
                    help="Intensity multiplier when a keyword is detected (e.g., 1.5)")

args = parser.parse_args()

# ====== CACHE UTILS ======
def load_cached_settings():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_cached_settings(settings):
    with open(CACHE_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

# ====== LOAD OR RESET SETTINGS ======
if args.reset and os.path.exists(CACHE_FILE):
    os.remove(CACHE_FILE)
    print("Cache reset.")

cached = load_cached_settings()

POST_ID = args.id or cached.get('post_id', 'gxvdih')
MIN_INTENSITY = args.minimum if args.minimum is not None else cached.get('min_intensity', 0.2)
MAX_UPVOTES = args.max_upvotes if args.max_upvotes is not None else cached.get('max_upvotes', 100)
KEYWORD_LIST = args.keywords.split(",") if args.keywords else cached.get('keywords', ["knot", "puppy", "gock", "stupid", "choke"])
KEYWORD_INTENSITY_MULTIPLIER = args.multiplier if args.multiplier is not None else cached.get('multiplier', 1.5)

save_cached_settings({
    'post_id': POST_ID,
    'min_intensity': MIN_INTENSITY,
    'max_upvotes': MAX_UPVOTES,
    'keywords': KEYWORD_LIST,
    'multiplier': KEYWORD_INTENSITY_MULTIPLIER
})

# ====== REDDIT SETUP ======
BUTTPLUG_SERVER_URL = config.get("buttplug_server_url", "ws://localhost:12345")
REDDIT_CLIENT_ID = config["reddit_client_id"]
REDDIT_SECRET = config["reddit_secret"]
REDDIT_USER_AGENT = config["reddit_user_agent"]


reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

seen_comment_ids = set()

# ====== INTENSITY CALCULATION ======
def calculate_intensity(post_score, multiplier=1.0):
    scaled = post_score / MAX_UPVOTES
    base_intensity = MIN_INTENSITY + (1.0 - MIN_INTENSITY) * scaled
    return min(base_intensity * multiplier, 1.0)

# ====== FETCH NEW COMMENTS ======
def get_new_comments(submission, seen_ids):
    submission._fetch()
    submission.comments.replace_more(limit=0)
    comments = submission.comments.list()
    return [comment for comment in comments if comment.id not in seen_ids]

# ====== VIBRATION ======
async def send_vibration(client, intensity):
    if client.devices:
        device = client.devices[0]
        if device.actuators:
            actuator = device.actuators[0]
            await actuator.command(intensity)
            print(f"💥 Sent vibration: {intensity:.2f} for {VIBRATION_DURATION:.1f}s")
            await asyncio.sleep(VIBRATION_DURATION)
            await actuator.command(0.0)
        else:
            print("No actuators on device.")
    else:
        print("No Buttplug devices connected.")

# ====== MAIN LOOP ======
async def main():
    client = Client("Intibot", ProtocolSpec.v3)
    connector = WebsocketConnector(BUTTPLUG_SERVER_URL, logger=client.logger)

    try:
        await client.connect(connector)
        await client.start_scanning()
        await asyncio.sleep(1)
        await client.stop_scanning()
    except Exception as e:
        print(f"Could not connect to Buttplug: {e}")
        return

    submission = reddit.submission(id=POST_ID)
    print(f"Monitoring post: {submission.title}")
    print(f"Max upvotes: {MAX_UPVOTES} → Intensity = 1.0")
    print(f"Min intensity: {MIN_INTENSITY}")
    print(f"Keyword triggers: {KEYWORD_LIST}")
    print(f"Keyword multiplier: {KEYWORD_INTENSITY_MULTIPLIER}")

    try:
        while True:
            new_comments = await asyncio.to_thread(get_new_comments, submission, seen_comment_ids)

            for comment in new_comments:
                seen_comment_ids.add(comment.id)

                print(f"\nNew comment by {comment.author}: {comment.body[:80]}")

                comment_text = comment.body.lower()
                if any(keyword in comment_text for keyword in KEYWORD_LIST):
                    multiplier = KEYWORD_INTENSITY_MULTIPLIER
                    print(f"Keyword detected → Boosting intensity to {multiplier:.2f}x")
                else:
                    multiplier = 1.0

                post_score = submission.score or 1
                intensity = calculate_intensity(post_score, multiplier)
                print(f"Post score: {post_score} → Vibration intensity: {intensity:.2f}")

                await send_vibration(client, intensity)

            await asyncio.sleep(1)

    except Exception as e:
        print(f"Runtime error: {e}")
    finally:
        await client.disconnect()
        print("Bot shut down.")

# ====== RUN ======
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user.")
