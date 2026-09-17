import os, urllib.request, re
from urllib.parse import urlparse
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
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '0',
        }],
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
        filepath = filename.rsplit('.', 1)[0] + '.mp3'
        return filepath, thumbnail_url

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
            f"<code>{escape(url[:80])}</code> is not a valid link.\n"
            "Please send a valid URL starting with <code>http://</code> or <code>https://</code>",
            parse_mode="HTML"
        )
        return
    

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
                
                if is_youtube_url(url):
                    short_url = extract_yt_short_url(url)
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(text="🎵 Convert to MP3", callback_data=f"convert_mp3:{short_url}"),
                            ]
                        ]
                    )
                    
                await message.answer_video(
                    video=FSInputFile(file_path),
                    reply_markup=keyboard if is_youtube_url(url) else None # если ссылка ютубовская то даем возможность конвертации в аудио
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

# логика инлайн кнопки convert to mp3

def download_cover_sync(url: str, save_path: str) -> bool:
    # cинхронная вспомогательная функция для скачивания обложки
    try:
        urllib.request.urlretrieve(url, save_path)
        return os.path.exists(save_path)
    except Exception as e:
        print(f"Error downloading cover: {e}")
        return False

@dp.callback_query(F.data.startswith("convert_mp3:"))
async def handle_audio_convertion(callback: CallbackQuery):
    video_url = callback.data.split("convert_mp3:", 1)[1]
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
        # 1. Скачиваем обложку (с уникальным именем на основе имени аудио)
        if thumb_url:
            covers_dir = Path("covers")
            covers_dir.mkdir(exist_ok=True)
            
            # Используем имя аудиофайла, чтобы избежать конфликтов при параллельных запросах
            temp_cover_path = covers_dir / f"cover_{Path(audio_path).stem}.jpg"
            
            # Запускаем синхронное скачивание в отдельном потоке
            cover_downloaded = await asyncio.to_thread(
                download_cover_sync, thumb_url, str(temp_cover_path)
            )
            
            if cover_downloaded:
                cover_for_audio = FSInputFile(temp_cover_path)

        # 2. Парсим Исполнителя и Название
        clean_path = Path(audio_path).stem
        if " – " in clean_path:
            performer, title = clean_path.split(" – ", 1)
        else:
            performer, title = "Unknown", clean_path

        # 3. Отправляем аудио в Telegram
        await callback.message.answer_audio(
            audio=FSInputFile(audio_path),
            title=title.strip(),
            performer=performer.strip(),
            thumbnail=cover_for_audio
        )
        
        # Удаляем временное статусное сообщение
        await status_msg.delete()

    except Exception as e:
            print(f"Error sending audio: {e}")
            await callback.message.answer("⚠️ Error sending audio file.")

    finally:
            # Guaranteed Cleanup (Очистка гарантированно выполнится даже при ошибке)
            if temp_cover_path and os.path.exists(temp_cover_path):
                try:
                    os.remove(temp_cover_path)
                except OSError:
                    pass

            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except OSError:
                    pass
            await callback.answer()
    

async def main():
    await dp.start_polling(bot)

asyncio.run(main())
