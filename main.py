import os
from dotenv import load_dotenv

import asyncio
from pathlib import Path
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
import yt_dlp

load_dotenv()

TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

MB = 1024 * 1024
size_limit = 50 * MB

class DownloadStates(StatesGroup):
    waiting_for_url = State()

def download_video_sync(url):
    options = {
        'color': 'no_color',
        "outtmpl": "downloads/%(id)s_%(title)s.%(ext)s",  # id предотвращает конфликты имён
        "format": "bestvideo+bestaudio/best",
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

            # Если объект оказался плейлистом, берём первый элемент
        if "entries" in info:
            if not info["entries"]:
                return False
            info = info["entries"][0]

        filename = ydl.prepare_filename(info)
        return filename

@dp.message(Command("download"))
async def start_download(message: Message, state: FSMContext):
    await message.answer("🔗 Please send a <b>video link</b> to start downloading.",
                         parse_mode="HTML")
    await state.set_state(DownloadStates.waiting_for_url)

@dp.message(DownloadStates.waiting_for_url)
async def process_url(message: Message, state: FSMContext):
    url = message.text
    await message.answer("Preparing to download the video...")
    try: 
        filename = await asyncio.to_thread(download_video_sync, url)

        file_path = Path(filename)
        if file_path.exists():
            if file_path.stat().st_size > size_limit:
                await message.answer("<b>The video size exceeds Telegram's 50-megabyte limit.</b> Try downloading the video in a lower resolution.",
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
            "<b>Video sent successfully!</b> /download — for another video",
            parse_mode="HTML")
        
        await state.clear()
    except Exception as e:
        await message.answer(f"{type(e).__name__}: {e}")
        await message.answer("Try again. Waiting for the video URL...")
        return # завершаем функцию тем самым заставляя снова выполниться process_url

@dp.message()
async def handle_message(message: Message):
    text = message.text
    
    if not text or not text.startswith(('http://', 'https://')):
        await message.answer("/download to use the bot")
        return

async def main():
    await dp.start_polling(bot)

asyncio.run(main())
