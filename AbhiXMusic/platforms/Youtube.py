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

# 🔥 AUTO-DETECT CONFIG
API_URL = getattr(config, 'API_URL', getattr(config, 'YOUR_API_URL', getenv("YOUR_API_URL", 'https://myloveisdimpi.online')))
API_KEY = getattr(config, 'API_KEY', getattr(config, 'YOUR_API_KEY', getenv("YOUR_API_KEY", 'DIMPI-SECRET-KEY')))

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S"
)
logger = logging.getLogger("Youtube")

HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}

def cookie_txt_file():
    folder_path = f"{os.getcwd()}/cookies"
    if not os.path.exists(folder_path): os.makedirs(folder_path)
    txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
    if not txt_files: return None
    return random.choice(txt_files)

# --- 🔥 MAIN API FUNCTION ---
async def download_via_api(link: str, media_type: str, message: Message = None):
    if not API_URL: return None
    
    if link.endswith("watch?v=") or not link.startswith("http"): 
        return None

    # Metadata Payload
    payload = {"url": link, "type": media_type, "quality": "best"}
    
    if message:
        try:
            payload["chat_id"] = message.chat.id
            payload["chat_title"] = message.chat.title or "Private"
            payload["requester_name"] = message.from_user.first_name if message.from_user else "Unknown"
        except: pass

    logger.info(f"📡 [API REQUEST] | 🔗 {link}")
    
    # Fix URL path
    base_url = API_URL.rstrip("/")
    if base_url.endswith("/download"): base_url = base_url.replace("/download", "")
    target_endpoint = f"{base_url}/download"

    async with aiohttp.ClientSession() as session:
        for attempt in range(3): 
            try:
                async with session.post(target_endpoint, json=payload, headers=HEADERS, timeout=60) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") in ["success", "done"]:
                            filename = os.path.basename(data.get("file"))
                            stream_url = f"{base_url}/stream/{filename}"
                            logger.info(f"✅ [API SUCCESS] | 🎵 {filename}")
                            return stream_url
                    elif resp.status in [400, 404]: 
                        return None 
                    await asyncio.sleep(2)
            except: pass
    return None

async def check_file_size(link):
    cookie_file = cookie_txt_file()
    if not cookie_file: return None
    try:
        proc = await asyncio.create_subprocess_exec("yt-dlp", "--cookies", cookie_file, "-J", link, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        return json.loads(stdout.decode()) if proc.returncode == 0 else None
    except: return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message: messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        return message.text[entity.offset : entity.offset + entity.length]
        return None

    def extract_id(self, link):
        if "youtu.be" in link: return link.split("/")[-1].split("?")[0]
        if "watch?v=" in link: return link.split("watch?v=")[1].split("&")[0]
        return None

    # 🔥 NEW: Fallback Search (Enhanced)
    async def fallback_details(self, link):
        try:
            loop = asyncio.get_running_loop()
            opts = {
                "quiet": True, 
                "no_warnings": True, 
                "cookiefile": cookie_txt_file(),
                "extract_flat": True,
                "force_generic_extractor": False
            }
            
            search_query = link if re.search(self.regex, link) else f"ytsearch1:{link}"

            def get_info():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(search_query, download=False)
                    return info['entries'][0] if 'entries' in info else info

            info = await loop.run_in_executor(None, get_info)
            if not info: return None, None, None, None, None

            title = info.get("title")
            vidid = info.get("id")
            dur = int(info.get("duration", 0) or 0)
            dur_min = f"{dur // 60}:{dur % 60:02d}"
            thumb = info.get("thumbnail") or f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"
            
            return title, dur_min, dur, thumb, vidid
        except Exception as e:
            logger.error(f"❌ Fallback Failed: {e}")
            return None, None, None, None, None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        clean_id = self.extract_id(link)
        if clean_id: link = self.base + clean_id

        try:
            results = VideosSearch(link, limit=1)
            res = (await results.next())["result"][0]
            return {
                "title": res["title"], "link": res["link"], "vidid": res["id"],
                "duration_min": res["duration"], "thumb": res["thumbnails"][0]["url"].split("?")[0]
            }, res["id"]
        except:
            pass
        
        logger.info(f"⚠️ Standard Search Failed for {link}, trying yt-dlp (FLAT)...")
        t, dm, _, th, vi = await self.fallback_details(link)
        if t:
            return {"title": t, "link": self.base + vi, "vidid": vi, "duration_min": dm, "thumb": th}, vi
        
        raise Exception("Track not found on YouTube.")

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        if "&" in link: link = link.split("&")[0]
        
        try:
            results = VideosSearch(link, limit=1)
            res = (await results.next())["result"][0]
            dur_sec = int(time_to_seconds(res["duration"])) if res["duration"] != "None" else 0
            return res["title"], res["duration"], dur_sec, res["thumbnails"][0]["url"].split("?")[0], res["id"]
        except: pass

        t, dm, ds, th, vi = await self.fallback_details(link)
        if t: return t, dm, ds, th, vi
        return "Unknown Song", "0:00", 0, "", ""

    async def title(self, link: str, videoid: Union[bool, str] = None):
        t, _, _, _, _ = await self.details(link, videoid)
        return t

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        _, d, _, _, _ = await self.details(link, videoid)
        return d

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        _, _, _, t, _ = await self.details(link, videoid)
        return t

    async def formats(self, link: str, videoid: Union[bool, str] = None): return [], link

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        res = (await VideosSearch(link, limit=10).next()).get("result")[query_type]
        return res["title"], res["duration"], res["thumbnails"][0]["url"].split("?")[0], res["id"]

    async def download(
        self, link: str, mystic, video: Union[bool, str] = None, videoid: Union[bool, str] = None,
        songaudio: Union[bool, str] = None, songvideo: Union[bool, str] = None, format_id: Union[bool, str] = None, title: Union[bool, str] = None,
    ) -> str:
        
        if videoid: link = self.base + link

        clean_id = self.extract_id(link)
        if clean_id: 
            link = self.base + clean_id
        elif "youtube.com" not in link and "youtu.be" not in link:
            try:
                data, _ = await self.track(link)
                if data: link = data['link']
            except: 
                return None, False

        # Try API
        media_type = "video" if (video or songvideo) else "audio"
        try:
            api_file = await download_via_api(link, media_type, message=mystic)
            if api_file: return api_file, True
        except: pass

        # Local Fallback
        loop = asyncio.get_running_loop()
        def local_dl():
            # 🔥 SWITCH TO ANDROID CLIENT (Better Success Rate)
            opts = {
                "outtmpl": "downloads/%(id)s.%(ext)s", "quiet": True, 
                "cookiefile": cookie_txt_file(), "nocheckcertificate": True,
                "extractor_args": {"youtube": {"player_client": ["android"]}}
            }
            if media_type == "audio":
                opts.update({"format": "bestaudio/best", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]})
            else:
                opts.update({"format": "bestvideo+bestaudio/best", "merge_output_format": "mp4"})
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                ext = "mp3" if media_type == "audio" else "mp4"
                return os.path.join("downloads", f"{info['id']}.{ext}")

        try:
            fpath = await loop.run_in_executor(None, local_dl)
            if fpath and os.path.exists(fpath): 
                return fpath, True
        except: pass
        
        return None, False
