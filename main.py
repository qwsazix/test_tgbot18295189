import os
from dotenv import load_dotenv
from html import escape

import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
import yt_dlp

load_dotenv()

TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

MB = 1024 * 1024
size_limit = 50 * MB

def download_video_sync(url):
    options = {
        'color': 'no_color',
        "outtmpl": "downloads/%(id)s_%(title)s.%(ext)s",
        "format": "bestvideo+bestaudio/best",
        'cookiefile': 'cookies.txt',
        "merge_output_format": "mp4",
        "quiet": True,
        "noplaylist": True,
        "no_warnings": False,
        "js_runtimes": {"node": {}},
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["web_embedded", "tv"]
            }
        },
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        if not info:
            return False

            # eсли объект оказался плейлистом, берём первый элемент
        if "entries" in info:
            if not info["entries"]:
                return False
            info = info["entries"][0]

        filename = ydl.prepare_filename(info)
        return filename

@dp.message(Command("start"))
async def handle_start(message: Message):
    await message.answer("Send me any video link and I'll download it for you! Powered by yt-dlp. <b>No commands required — just paste the URL right here.</b>",
                         parse_mode="HTML")

@dp.message()
async def process_url(message: Message, state: FSMContext):
    url = message.text  
    
    if not url or not url.startswith(('http://', 'https://')):
        await message.answer(
            "⚠️ <b>Invalid link format</b>\n"
            f"<code>{escape(url)}</code> is not a valid link.\n"
            "Please send a valid URL starting with <code>http://</code> or <code>https://</code>",
            parse_mode="HTML"
        )
        return
    
    await message.answer(
        "⏳ <b>Processing link...</b>", 
        parse_mode="HTML"
    )
    try: 
        filename = await asyncio.to_thread(download_video_sync, url)

        file_path = Path(filename)
        if file_path.exists():
            if file_path.stat().st_size > size_limit:
                await message.answer("<b>The video size exceeds Telegram's 50-megabyte limit.</b> Try to download another video.",
                                    parse_mode="HTML")
                await message.answer("Waiting for the video URL...")
                file_path.unlink()
                return
            else:
                await message.answer("📥 <b>Downloaded!</b> Uploading to chat...",
                                     parse_mode="HTML")
                try:
                    await message.answer_video(FSInputFile(file_path))
                finally:
                    file_path.unlink()
        else:
            await message.answer("Unexpected error occured! Try again")
            await message.answer("Waiting for the video URL...")
            return
        
        await message.answer(
            "<b>✅ Done!</b> Ready for the next URL!",
            parse_mode="HTML")
        
        await state.clear()
    except Exception as e:
        await message.answer(f"{type(e).__name__}: {e}")
        await message.answer("Try again! <b>Waiting for the video URL...</b>", parse_mode="HTML")
        return # завершаем функцию тем самым заставляя снова выполниться process_url


async def main():
    await dp.start_polling(bot)

asyncio.run(main())
