import os, re
from urllib.parse import urlparse
from dotenv import load_dotenv
from html import escape
from datetime import datetime

import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, URLInputFile, CallbackQuery
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

VALID_HOSTS = {
    'youtube.com',
    'www.youtube.com',
    'm.youtube.com',
    'youtu.be',
    'music.youtube.com',
    'www.youtube-nocookie.com'
}

    # укорачиваем юрл ютуба, чтобы он поместился в колбекдата инлайн кнопки
def extract_yt_short_url(url: str) -> str | None:
    # ищем 11-значный ID видео YouTube
    pattern = r'(?:v=|\/embed\/|\/shorts\/|youtu\.be\/)([0-9A-Za-z_-]{11})'
    match = re.search(pattern, url)
    if match:
        video_id = match.group(1) or match.group(2)
        return f"https://youtu.be/{video_id}"
    return None

    # проверка принадлежит ли отправленный юрл ютубу
def is_youtube_url(url: str) -> bool:
    # добавляем схему, если пользователь ввёл ссылку без http/https
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        parsed = urlparse(url)
        # hostname автоматически приводит домен к нижнему регистру
        return parsed.hostname in VALID_HOSTS
    except Exception:
        return False


def download_audio_sync(url):
    options = {
        'color': 'no_color',
        'outtmpl': 'audio/%(channel)s – %(title)s.%(ext)s',
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'cookiefile': 'cookies.txt',
        'quiet': True,
        'noplaylist': True,
        'no_warnings': False,
        'js_runtimes': {"node": {}},
        'http_headers': {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        },
        'extractor_args': {
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

def download_video_sync(url):
    options = {
        'color': 'no_color',
        'outtmpl': 'downloads/%(channel)s – %(title)s.%(ext)s',
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'cookiefile': 'cookies.txt',
        'quiet': True,
        'noplaylist': True,
        'no_warnings': False,
        'js_runtimes': {"node": {}},
        'http_headers': {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        },
        'extractor_args': {
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
    
def get_video_metadata(url):
    with yt_dlp.YoutubeDL() as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            return False

            # eсли объект оказался плейлистом, берём первый элемент
        if "entries" in info:
            if not info["entries"]:
                return False
            info = info["entries"][0]
            
        raw_date = info.get("upload_date")
        formatted_date = None
        if raw_date:
            formatted_date = datetime.strptime(raw_date, "%Y%m%d").strftime("%d.%m.%Y")

        return {
            "title": info.get("title"),                  # Название видео
            "author": info.get("uploader"),              # Имя автора / канала
            "upload_date": formatted_date,               # Дата загрузки (в отформатированном виде)
            "thumb_url": info.get("thumbnail"),      # Ссылка на превью
            "views": info.get("view_count"),             # Количество просмотров
            "description": info.get("description")       # Описание видео
        }

@dp.message(Command("start"))
async def handle_start(message: Message):
    await message.answer("Send me any video link and I'll download it for you! Powered by yt-dlp. <b>No commands required — just paste the URL right here.</b>",
                         parse_mode="HTML")

@dp.message()
async def process_url(message: Message):
    url = message.text  
    
    if not url or not url.startswith(('http://', 'https://')):
        await message.answer(
            "⚠️ <b>Invalid link format</b>\n"
            f"<code>{escape(url[:100])}</code> is not a valid link.\n"
            "Please send a valid URL starting with <code>http://</code> or <code>https://</code>",
            parse_mode="HTML"
        )
        return

    try:
        result = await asyncio.to_thread(get_video_metadata, url)
        if not result:
            await message.answer('❌ Could not retrieve video metadata.')
            return
        
        data = result
        
        if is_youtube_url(url):
            print(data['thumb_url'])
            short_url = extract_yt_short_url(url)
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="🎦 Download video", callback_data=f"vid:{short_url}"),
                        InlineKeyboardButton(text="🎵 Download audio", callback_data=f"aud:{short_url}"),
                    ]
                ]
            )
            
            await message.answer_photo(
                photo=URLInputFile(data['thumb_url']),
                caption=f"<b>Title:</b> {data['title']}\n<b>Author:</b> {data['author']}\n<b>Upload date:</b> {data['upload_date']}\n\n<b>Choose format to download:</b>", 
                reply_markup=keyboard,
                parse_mode="HTML"
                )
        else:
            # если ссылка не ютубовская сразу скачиваем и отправляем видео, не предлагая форматы
            await proccess_and_send_video(url, message)
        
    except Exception as e:
            # ловим ошибки yt_dlp и выводим их пользователю
        await message.answer(f"{type(e).__name__}: {e}")
        await message.answer("Try again! <b>Waiting for the video URL...</b>", parse_mode="HTML")
        return
    
# универсальная функция для скачивания и отправки видео    
async def proccess_and_send_video(url:str, message: Message):
    try: 
        status_msg = await message.answer(
            "⏳ <b>Processing link...</b>", 
            parse_mode="HTML"
        )
        result = await asyncio.to_thread(download_video_sync, url)
        if result:
            filename = result

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
                await status_msg.edit_text("📥 <b>Downloaded!</b> Uploading to chat...",
                                        parse_mode="HTML")
                    
                await message.answer_video(
                    video=FSInputFile(file_path)
                    )
                
                # удаляем видео с диска
                file_path.unlink()  
                #в самом конце можно удалить статусное сообщение
                await status_msg.delete()
        else:
            # если по какой-то причине файла вообще не существует, то сообщаем об ошибке
            await status_msg.edit_text("Unexpected error occured! Try again")
            await message.answer("Waiting for the video URL...")
            return
        
    except Exception as e:
        # ловим ошибки yt_dlp и выводим их пользователю
        await message.answer(f"{type(e).__name__}: {e}")
        await message.answer("Try again! <b>Waiting for the video URL...</b>", parse_mode="HTML")
        return # завершаем функцию тем самым заставляя снова выполниться process_url

        
        
# хэндлеры для инлайн кнопок
@dp.callback_query(F.data.startswith("vid:"))
async def handle_video_download(callback: CallbackQuery):
    url = callback.data.split("vid:", 1)[1]
    await proccess_and_send_video(url, callback.message)
    await callback.answer()


@dp.callback_query(F.data.startswith("aud:"))
async def handle_audio_download(callback: CallbackQuery):
    video_url = callback.data.split("aud:", 1)[1]
    audio_path = None
    thumb_url = None
    
    if not video_url:
        await callback.message.answer("⚠️ Invalid video data.")
        await callback.answer()
        return
    
    status_msg = await callback.message.answer("⏳ Processing audio, please wait...")
    
        # Скачиваем аудио
    result = await asyncio.to_thread(download_audio_sync, video_url)
    if not result or not result[0]:
        await status_msg.edit_text("⚠️ Failed to download audio.")
        return
        
    audio_path, thumb_url = result
    
    try:
        # парсим Исполнителя и Название
        clean_path = Path(audio_path).stem
        if " – " in clean_path:
            performer, title = clean_path.split(" – ", 1)
        else:
            performer, title = "Unknown", clean_path

        # отправляем аудио в Telegram
        await callback.message.answer_audio(
            audio=FSInputFile(audio_path),
            title=title.strip(),
            performer=performer.strip(),
            thumbnail=URLInputFile(thumb_url)
        )
        
        # Удаляем временное статусное сообщение
        await status_msg.delete()
    except Exception as e:
            await callback.message.answer("⚠️ Error sending audio file.")
    finally:
            # очистка гарантированно выполнится даже при ошибке
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except OSError:
                    pass
            await callback.answer()

async def main():
    await dp.start_polling(bot)

asyncio.run(main())
