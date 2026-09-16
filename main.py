import os, ffmpeg, urllib.request
from dotenv import load_dotenv
from html import escape

import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp

load_dotenv()

TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

MB = 1024 * 1024
size_limit = 50 * MB

keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🎵 Convert to MP3", callback_data="convert_mp3"),
        ]
    ]
)

def download_video_sync(url):
    options = {
        'color': 'no_color',
        "outtmpl": "downloads/%(channel)s – %(title)s.%(ext)s",
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
            
        thumbnail_url = info.get("thumbnail")

        filename = ydl.prepare_filename(info)
        return filename, thumbnail_url

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
        result = await asyncio.to_thread(download_video_sync, url)
        if result:
            filename, thumbnail_url = result

        file_path = Path(filename)
        if file_path.exists():
            # если размер скачанного видео превышает 50МБ ограничение телеграмовского апи
            if file_path.stat().st_size > size_limit:
                await message.answer("<b>The video size exceeds Telegram's 50-megabyte limit.</b> Try to download another video.",
                                    parse_mode="HTML")
                await message.answer("Waiting for the video URL...")
                file_path.unlink()
                return
            else:
                # если размер в норме, отправляем видео
                await message.answer("📥 <b>Downloaded!</b> Uploading to chat...",
                                     parse_mode="HTML")
                
                await message.answer_video(
                    video=FSInputFile(file_path),
                    reply_markup=keyboard
                    )
                
                await state.update_data(last_video_path=str(file_path), thumbnail_url=str(thumbnail_url), video_url = url)
                
                # удаляем видео с диска
                file_path.unlink()
        else:
            # если по какой-то причине файла вообще не существует, то сообщаем об ошибке
            await message.answer("Unexpected error occured! Try again")
            await message.answer("Waiting for the video URL...")
            return
        
    except Exception as e:
        # ловим ошибки yt_dlp и выводим их пользователю
        await message.answer(f"{type(e).__name__}: {e}")
        await message.answer("Try again! <b>Waiting for the video URL...</b>", parse_mode="HTML")
        return # завершаем функцию тем самым заставляя снова выполниться process_url


# сделать 2 инлайн кнопки после выкачивания видео: конвертация в мп3 или в гиф

@dp.callback_query(F.data == "convert_mp3")
async def handle_audio_convertion(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    thumb_url = data.get("thumbnail_url")
    video_path = data.get("last_video_path")
    video_url = data.get("video_url")
    
    if not video_path:
        await callback.message.answer("⚠️ Session expired or invalid video data.")
        await callback.answer()
        return
    
    await callback.message.answer(f"Please wait..")
    
    if not os.path.exists(video_path):
        result = await asyncio.to_thread(download_video_sync, video_url)
        if result:
            video_path, thumb_url = result

    if thumb_url:
        try:
            os.makedirs("covers", exist_ok=True)
            
            temp_cover_path = "covers/temp_cover.jpg"
            urllib.request.urlretrieve(thumb_url, temp_cover_path)
            
            if os.path.exists(temp_cover_path):
                cover_for_audio = FSInputFile(temp_cover_path)
                
        except Exception as e:
            print(f"Error downloading cover: {e}")
    

    video_name = Path(video_path).name
    clean_path = Path(video_name).stem
    output_path = f"downloads/{clean_path}.mp3"
    
    
    def convert_to_mp3(input_path: str, output_path: str):            
        return(
            ffmpeg.input(input_path)
            .output(
                output_path,
                **{
                    'c:a': 'libmp3lame',
                    'qscale:a': 0
                }
            )
            .overwrite_output()
            .run()
        )
        
    await asyncio.to_thread(convert_to_mp3, video_path, output_path)
    
    if " – " in clean_path:
        performer, title = clean_path.split(" – ", 1)
    else:
        performer, title = "Unknown", clean_path
        
    await callback.message.answer_audio(
        FSInputFile(output_path),
        title=title.strip(),
        performer=performer.strip(),
        thumbnail=cover_for_audio
    )
    
    # очищаем временные файлы 1)обложку 2)видео 3)аудио
    if cover_for_audio and os.path.exists(temp_cover_path):
        os.remove(temp_cover_path)
        
    if os.path.exists(video_path):
        os.remove(video_path)
        
    await asyncio.sleep(5)
    if os.path.exists(output_path):
        os.remove(output_path)
    
    await callback.answer()

async def main():
    await dp.start_polling(bot)

asyncio.run(main())
