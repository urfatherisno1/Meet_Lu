import asyncio
import os
import re
import json
import glob
import random
import logging
import time
import aiohttp
from typing import Union

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from youtubesearchpython.__future__ import VideosSearch

from AbhiXMusic.utils.database import is_on_off
from AbhiXMusic.utils.formatters import time_to_seconds
import config
from os import getenv

# -----------------------------
# 🔥 DimpiAPI Configuration
# -----------------------------
API_URL = getattr(config, 'YOUR_API_URL', getenv("YOUR_API_URL", 'https://myloveisdimpi.online'))
API_KEY = getattr(config, 'YOUR_API_KEY', getenv("YOUR_API_KEY", 'DIMPI-SECRET-KEY'))

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S"
)
logger = logging.getLogger("Youtube")

def cookie_txt_file():
    cookie_dir = f"{os.getcwd()}/cookies"
    if not os.path.exists(cookie_dir): os.makedirs(cookie_dir)
    cookies_files = [f for f in os.listdir(cookie_dir) if f.endswith(".txt")]
    if not cookies_files: return None
    return os.path.join(cookie_dir, random.choice(cookies_files))

# --- 🔥 MAIN API FUNCTION (Handles Audio & Video via POST) ---
async def download_via_api(link: str, media_type: str, message: Message = None):
    if not API_URL: return None
    
    # Clean URL for API
    if "&" in link and "watch?v=" in link:
        link = link.split("&")[0]

    start_time = time.time()
    requester = "Unknown"
    chat_title = "Private"
    
    payload = {"url": link, "type": media_type, "quality": "best"}
    
    if message:
        try:
            payload.update({
                "chat_id": message.chat.id,
                "chat_title": message.chat.title or "Private",
                "requester_name": message.from_user.first_name if message.from_user else "Unknown",
            })
            requester = payload["requester_name"]
            chat_title = payload["chat_title"]
        except: pass

    logger.info(f"📡 [API REQUEST] | 👤 {requester} | 🏘 {chat_title} | 🔗 {link}")
    
    target_endpoint = f"{API_URL}/download"
    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        for attempt in range(5): # Retry 5 times
            try:
                async with session.post(target_endpoint, json=payload, headers=headers, timeout=120) as resp:
                    if resp.status != 200:
                        logger.warning(f"⚠️ API Status: {resp.status} (Attempt {attempt+1})")
                        await asyncio.sleep(2)
                        continue

                    data = await resp.json()
                    status = data.get("status", "").lower()

                    if status == "success" or status == "done":
                        file_path = data.get("file")
                        filename = os.path.basename(file_path)
                        stream_url = f"{API_URL}/stream/{filename}"
                        elapsed = time.time() - start_time
                        logger.info(f"✅ [API SUCCESS] | 🎵 {filename} | ⏱ {elapsed:.2f}s")
                        return stream_url
                    
                    elif status == "downloading":
                        await asyncio.sleep(5)
                    else:
                        logger.error(f"❌ API Error: {data.get('message')}")
                        break
            except Exception as e:
                logger.error(f"❌ Connection Error: {e}")
                await asyncio.sleep(2)
    return None

# --- Helper for Local DL ---
async def check_file_size(link):
    cookie_file = cookie_txt_file()
    if not cookie_file: return None
    try:
        proc = await asyncio.create_subprocess_exec("yt-dlp", "--cookies", cookie_file, "-J", link, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        return json.loads(stdout.decode()) if proc.returncode == 0 else None
    except: return None

async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, errorz = await proc.communicate()
    return out.decode("utf-8") if not errorz else errorz.decode("utf-8")

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.listbase = "https://youtube.com/playlist?list="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message: messages.append(message_1.reply_to_message)
        text, offset, length = "", None, None
        for message in messages:
            if offset: break
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text, offset, length = message.text or message.caption, entity.offset, entity.length
                        break
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK: return entity.url
        return text[offset : offset + length] if offset is not None else None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        try:
            results = VideosSearch(link, limit=1)
            res = (await results.next())["result"][0]
            duration_sec = int(time_to_seconds(res["duration"])) if res["duration"] != "None" else 0
            return res["title"], res["duration"], duration_sec, res["thumbnails"][0]["url"].split("?")[0], res["id"]
        except: return "Unknown Song", "0:00", 0, "", ""

    async def title(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]: return result["title"]

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]: return result["duration"]

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        results = VideosSearch(link, limit=1)
        for result in (await results.next())["result"]: return result["thumbnails"][0]["url"].split("?")[0]

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        
        # Try API first
        api_video = await download_via_api(link, "video")
        if api_video: return 1, api_video

        # Fallback Local
        cookie_file = cookie_txt_file()
        if not cookie_file: return 0, "No cookies."
        proc = await asyncio.create_subprocess_exec("yt-dlp", "--cookies", cookie_file, "-g", "-f", "best[height<=?720]", f"{link}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cookie_file = cookie_txt_file()
        if not cookie_file: return []
        playlist = await shell_cmd(f"yt-dlp -i --get-id --flat-playlist --cookies {cookie_file} --playlist-end {limit} --skip-download {link}")
        return [k for k in playlist.split("\n") if k]

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        try:
            results = VideosSearch(link, limit=1)
            res = (await results.next())["result"][0]
            data = {"title": res["title"], "link": res["link"], "vidid": res["id"], "duration_min": res["duration"], "thumb": res["thumbnails"][0]["url"].split("?")[0]}
            return data, res["id"]
        except:
            return {"title": "Unknown Song", "link": link, "vidid": "", "duration_min": "0:00", "thumb": ""}, ""

    async def formats(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        cookie_file = cookie_txt_file()
        if not cookie_file: return [], link
        ydl = yt_dlp.YoutubeDL({"quiet": True, "cookiefile" : cookie_file})
        with ydl:
            formats_available = []
            r = ydl.extract_info(link, download=False)
            for f in r["formats"]:
                if "dash" not in str(f.get("format")).lower():
                    formats_available.append({"format": f["format"], "filesize": f.get("filesize"), "format_id": f["format_id"], "ext": f["ext"], "format_note": f.get("format_note"), "yturl": link})
        return formats_available, link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        res = (await VideosSearch(link, limit=10).next()).get("result")[query_type]
        return res["title"], res["duration"], res["thumbnails"][0]["url"].split("?")[0], res["id"]

    async def download(
        self, link: str, mystic, video: Union[bool, str] = None, videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None, format_id: Union[bool, str] = None, title: Union[bool, str] = None,
    ) -> str:
        
        start_dl_time = time.time()
        if videoid: link = self.base + link

        # 1. SEARCH LOGIC (Resolve Ghost Links)
        if "youtube.com" not in link and "youtu.be" not in link:
            try:
                results = VideosSearch(link, limit=1)
                res = (await results.next())["result"][0]
                link = res["link"]
            except: pass 

        # 2. API DOWNLOAD (Fixed Trigger)
        media_type = "video" if (video or songvideo) else "audio"
        try:
            # Check for ANY youtube link pattern
            if ("youtube.com" in link or "youtu.be" in link):
                api_file = await download_via_api(link, media_type, message=mystic)
                if api_file: return api_file, True
        except Exception as e:
            logger.error(f"API Trigger Failed: {e}")

        # 3. LOCAL DOWNLOAD (Fallback)
        logger.info(f"⬇️ Local Fallback: {link}")
        loop = asyncio.get_running_loop()
        cookies = cookie_txt_file()

        def local_dl(type_):
            opts = {
                "outtmpl": "downloads/%(id)s.%(ext)s", 
                "geo_bypass": True, 
                "nocheckcertificate": True, 
                "quiet": True, 
                "no_warnings": True,
                "cookiefile": cookies,
                "extractor_args": {"youtube": {"player_client": ["ios"]}}
            }
            if type_ == "audio":
                opts["format"] = "bestaudio/best"
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
            else:
                opts["format"] = "bestvideo+bestaudio/best"
                opts["merge_output_format"] = "mp4"
            
            # Smart Search if not direct link
            dl_link = link
            if "youtube.com" not in dl_link and "youtu.be" not in dl_link:
                dl_link = f"ytsearch1:{dl_link}"

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(dl_link, download=True)
                if 'entries' in info: info = info['entries'][0]
                ext = "mp3" if type_ == "audio" else "mp4"
                return os.path.join("downloads", f"{info['id']}.{ext}")

        try:
            type_ = "video" if (video or songvideo) else "audio"
            fpath = await loop.run_in_executor(None, lambda: local_dl(type_))
            
            if fpath and os.path.exists(fpath):
                file_size = os.path.getsize(fpath) / (1024 * 1024)
                elapsed = time.time() - start_dl_time
                logger.info(f"✅ [LOCAL SUCCESS] | 🎵 {os.path.basename(fpath)} | 📦 {file_size:.2f} MB | ⏱ {elapsed:.2f}s")
                return fpath, True
                
        except Exception as e:
            logger.error(f"❌ Local Download Failed: {e}")
            return None, False
        
        # 🔥 CRITICAL FIX: Return tuple even if everything fails
        return None, False