import os
import time
import json
import re
import requests
import subprocess
import logging
import random
import html
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(r'c:\youtubehabit', 'daemon.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Configuration from .env
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_PATH = r'c:\youtubehabit'
WEBSITE_PATH = os.path.join(BASE_PATH, 'index.html')
SEEN_VIDEOS_FILE = os.path.join(BASE_PATH, 'seen_videos.json')
RECORDS_FILE = os.path.join(BASE_PATH, 'records.json')
SUBSCRIPTION_FILE = os.path.join(BASE_PATH, '訂閱.txt')

if not DEEPSEEK_API_KEY:
    logging.error("DEEPSEEK_API_KEY not found in .env")
    exit(1)

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

def get_telegram_chat_id():
    """Attempt to get chat ID from the latest bot update."""
    global TELEGRAM_CHAT_ID
    if TELEGRAM_CHAT_ID:
        return TELEGRAM_CHAT_ID
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        resp = requests.get(url, timeout=10).json()
        if resp.get("ok") and resp.get("result"):
            # Get chat ID from the last message
            last_chat_id = resp["result"][-1]["message"]["chat"]["id"]
            logging.info(f"Automatically detected Telegram Chat ID: {last_chat_id}")
            return str(last_chat_id)
    except Exception as e:
        logging.error(f"Error getting Telegram Chat ID: {e}")
    return None

def send_telegram_msg(message):
    global TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN:
        return
    
    if not TELEGRAM_CHAT_ID:
        TELEGRAM_CHAT_ID = get_telegram_chat_id()
    
    if not TELEGRAM_CHAT_ID:
        logging.warning("Telegram Chat ID not found. Please send a message to the bot first.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logging.error(f"Failed to send Telegram message (HTML): {e}")
        if 'resp' in locals() and resp is not None:
             logging.error(f"Telegram response: {resp.text}")
        
        # Fallback to plain text
        try:
            payload['parse_mode'] = None
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            logging.info("Sent Telegram message using plain text fallback.")
        except Exception as e2:
            logging.error(f"Failed to send Telegram message (Plain Text): {e2}")

def save_json(filepath, data):
    try:
        temp_file = filepath + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(temp_file, filepath)
    except Exception as e:
        logging.error(f"Error saving JSON to {filepath}: {e}")

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading JSON from {filepath}: {e}")
    return default

def get_subscriptions():
    """Load subscriptions from file and filter for relevant (Finance/Crypto) channels."""
    if not os.path.exists(SUBSCRIPTION_FILE):
        logging.warning(f"Subscription file not found: {SUBSCRIPTION_FILE}")
        return []
    
    try:
        with open(SUBSCRIPTION_FILE, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        # Finance/Crypto keywords to filter relevant channels
        keywords = [
            '股市', '財經', '投資', '比特幣', '加密', '美股', '港股', '幣圈', '金融', 
            'Bitcoin', 'Crypto', 'Stock', 'Market', 'BTC', 'ETH', 'ADA', 'XRP', 
            '分析', '行情', '策略', '金', '銀', '油', 'Money', 'Wealth', 'Trading', 
            'Invest', 'Finance', 'Economics', 'Dividend', 'Option', 'Future', 'Fund',
            'Business', 'Capital', 'Asset'
        ]
        
        relevant_subs = [
            sub for sub in lines 
            if any(kw.lower() in sub.lower() for kw in keywords)
        ]
        
        logging.info(f"Loaded {len(relevant_subs)} relevant subscriptions out of {len(lines)} total.")
        return relevant_subs
    except Exception as e:
        logging.error(f"Error loading subscriptions: {e}")
        return []

def get_transcript(video_id):
    try:
        # Try getting Chinese or English transcripts directly
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['zh-TW', 'zh-HK', 'zh-CN', 'en'])
        return " ".join([t['text'] for t in transcript])
    except Exception as e:
        try:
            # Fallback: List all available and find one
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = transcript_list.find_transcript(['zh-TW', 'zh-HK', 'zh-CN', 'en'])
            data = transcript.fetch()
            return " ".join([t['text'] for t in data])
        except Exception as e2:
            logging.warning(f"Could not get transcript for {video_id}: {e2}")
            return None

def summarize_with_transcript(title, transcript):
    prompt = f"標題：{title}\n字幕內容：{transcript[:8000]}" if transcript else f"標題：{title}"
    sys_msg = """您是一位資深的首席財經分析師。請針對提供的影片標題及字幕內容，撰寫一份精煉的分析。
    請直接以「重點列表 (Point Form)」輸出，嚴禁使用任何小標題（如「核心觀點」、「關鍵細節」、「投資評估」等）。
    內容應具體描述影片中的關鍵數據、市場動態、明確的投資價值或趨勢預測。請務必提到影片中具體的數字、標的名稱、或特定觀點，絕對避免如「影片提到了數據」、「分析了市場趨勢」等概括、空泛且不具實質內容的描述。
    請使用正式繁體中文，總字數控制在 500 字以內。若原始內容為英文，請務必翻譯並以流暢的中文撰寫。若無字幕，請根據標題進行推理並註明「（根據標題深度推演）」。"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": sys_msg}, {"role": "user", "content": prompt}],
            timeout=45
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Error summarizing {title}: {e}")
        return title

def is_within_2_weeks(time_str):
    if not time_str: return True
    time_str = time_str.lower()
    if any(x in time_str for x in ["minute", "hour", "day", "分鐘", "小時", "天"]):
        match = re.search(r'(\d+)', time_str)
        return int(match.group(1)) <= 14 if match and ("day" in time_str or "天" in time_str) else True
    if any(x in time_str for x in ["week", "週", "周"]):
        match = re.search(r'(\d+)', time_str)
        return int(match.group(1)) <= 2 if match else True
    return False

def search_youtube(keyword):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}
    url = f"https://www.youtube.com/results?search_query={keyword}&sp=EgQIBBAB"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        # Handle cases where ytInitialData might be missing or structured differently
        match = re.search(r'var ytInitialData = (\{.*?\});', resp.text)
        if not match:
            logging.warning(f"Could not find ytInitialData for keyword: {keyword}")
            return []
            
        data = json.loads(match.group(1))
        
        # Navigate safely through the JSON structure
        try:
            items = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents']
        except KeyError:
            logging.warning(f"Unexpected JSON structure for keyword: {keyword}")
            return []

        videos = []
        for item in items:
            if 'itemSectionRenderer' in item:
                for content in item['itemSectionRenderer']['contents']:
                    if 'videoRenderer' in content:
                        v = content['videoRenderer']
                        t_str = v.get('publishedTimeText', {}).get('simpleText', '')
                        
                        # Basic data extraction
                        video_id = v.get('videoId')
                        title = v.get('title', {}).get('runs', [{}])[0].get('text', 'No Title')
                        channel = v.get('longBylineText', {}).get('runs', [{}])[0].get('text', 'No Channel')

                        if is_within_2_weeks(t_str):
                            videos.append({
                                'id': video_id, 
                                'title': title, 
                                'channel': channel, 
                                'time': t_str
                            })
        return videos
    except Exception as e:
        logging.error(f"Error searching YouTube for '{keyword}': {e}")
        return []

def update_website(all_records):
    # Keep only most recent 15 for the schedule
    recent = all_records[-15:]
    recent.reverse() # Show newest first in schedule
    
    try:
        if not os.path.exists(WEBSITE_PATH):
            logging.error(f"Website file not found at {WEBSITE_PATH}")
            return

        with open(WEBSITE_PATH, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        js_data = []
        for r in recent:
            # Metadata and Title formatting
            word_count = len(r.get('summary', ''))
            meta_header = f"【⏱️ {r.get('time', '未知')} | 🔄 {r.get('processed_at', '未知')} | 📝 {word_count} 字】"
            # Subject first
            display_content = f"📌 主題：{r.get('title', '無標題')}\n\n{meta_header}\n\n{r.get('summary', '無摘要')}"
            js_data.append({"summary": display_content, "channel": r.get('channel', '未知頻道'), "url": f"https://www.youtube.com/watch?v={r['id']}"})
        
        json_str = json.dumps(js_data, ensure_ascii=False).replace('\\', '\\\\')
        # Use more robust replacement
        pattern = r'const videos = \[.*?\];'
        replacement = f"const videos = {json_str};"
        if re.search(pattern, html_content, flags=re.DOTALL):
            new_html = re.sub(pattern, replacement, html_content, flags=re.DOTALL)
            with open(WEBSITE_PATH, 'w', encoding='utf-8') as f:
                f.write(new_html)
        else:
            logging.error("Could not find 'const videos = [...];' pattern in index.html")
    except Exception as e:
        logging.error(f"Error updating index.html: {e}")

def git_push():
    try:
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Dashboard update {datetime.now().strftime('%H:%M')}"], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        logging.info("Git push successful")
    except subprocess.CalledProcessError as e:
        logging.warning(f"Git push failed: {e.stderr.decode() if e.stderr else e}")
    except Exception as e:
        logging.error(f"Git push error: {e}")

def supabase_sync(records):
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return
    headers = {
        "apikey": SUPABASE_ANON_KEY, 
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}", 
        "Content-Type": "application/json", 
        "Prefer": "resolution=merge-duplicates"
    }
    data = [{"id": r['id'], "title": r['title'], "channel": r['channel'], "summary": r['summary'], "url": f"https://www.youtube.com/watch?v={r['id']}"} for r in records]
    try:
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/youtube_clips", headers=headers, json=data, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logging.error(f"Supabase sync failed: {e}")

def main():
    logging.info("AI YouTube Subscription Monitor V1 (Safe & Logged) Started...")
    seen_ids = set(load_json(SEEN_VIDEOS_FILE, []))
    all_records = load_json(RECORDS_FILE, [])
    
    # Load subscriptions once (or reload every cycle if dynamic updates needed)
    subscription_channels = get_subscriptions()
    logging.info(f"Loaded {len(subscription_channels)} channels to monitor.")
    
    while True:
        logging.info("Cycle started...")
        new_batch = []
        
        # Batch processing: Randomly select 50 channels to check per cycle to manage rate limits/time
        # Time complexity: 50 searches * ~2s = 100s + summary time. 
        # Summary time for 5 videos = 5 * 10s = 50s. Total < 3 mins. Safe for 5 min sleep.
        if not subscription_channels:
             logging.warning("No subscriptions loaded. Please check 訂閱.txt")
             current_batch_subs = []
        else:
            current_batch_subs = random.sample(subscription_channels, min(50, len(subscription_channels)))
        
        if current_batch_subs:
            logging.info(f"Checking {len(current_batch_subs)} channels in this cycle: {current_batch_subs[:5]}...")

        for sub_name in current_batch_subs:
            # Search for the channel to find recent videos
            results = search_youtube(sub_name)
            
            for vid in results:
                # Basic fuzzy matching for channel name to ensure it's the right channel
                if sub_name.lower() not in vid['channel'].lower() and vid['channel'].lower() not in sub_name.lower():
                    continue

                if vid['id'] in seen_ids: continue
                
                logging.info(f"Found new video from {vid['channel']}: {vid['title']}")
                transcript = get_transcript(vid['id'])
                vid['summary'] = summarize_with_transcript(vid['title'], transcript)
                if not transcript:
                    vid['summary'] = "⚠️⚠️⚠️【注意：無字幕，以下內容為 AI 看標題說故事，僅供參考】⚠️⚠️⚠️\n\n" + vid['summary']
                vid['processed_at'] = datetime.now().strftime('%m-%d %H:%M')
                new_batch.append(vid)
                seen_ids.add(vid['id'])
                
                # Send to Telegram (HTML Mode with escaping)
                word_count = len(vid['summary'])
                safe_title = html.escape(vid['title'])
                safe_summary = html.escape(vid['summary'])
                
                tg_msg = f"<b>📌 主題：{safe_title}</b>\n\n" \
                         f"📺 <b>頻道</b>: {html.escape(vid['channel'])}\n" \
                         f"⏱️ <b>時間</b>: {vid.get('time', '未知')}\n" \
                         f"🔄 <b>抓取</b>: {vid.get('processed_at', '未知')}\n" \
                         f"📝 <b>字數</b>: {word_count}\n\n" \
                         f"{safe_summary}\n\n" \
                         f"🔗 <a href='https://www.youtube.com/watch?v={vid['id']}'>觀看影片</a>"
                send_telegram_msg(tg_msg)

                if len(new_batch) >= 5: break
            if len(new_batch) >= 5: break

        if new_batch:
            all_records.extend(new_batch)
            all_records = all_records[-200:] # Keep last 200 records locally
            save_json(RECORDS_FILE, all_records)
            save_json(SEEN_VIDEOS_FILE, list(seen_ids))
            supabase_sync(new_batch)
            logging.info(f"Recorded {len(new_batch)} new videos.")
            
        update_website(all_records)
        git_push()
        
        logging.info("Cycle finished. Sleeping 5m...")
        time.sleep(300)

if __name__ == "__main__":
    main()
