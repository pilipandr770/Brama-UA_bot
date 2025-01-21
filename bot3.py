import os
import openai
import pytesseract
import requests

from io import BytesIO
from PIL import Image, ImageOps, ImageEnhance
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------- Завантаження змінних середовища ---------------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_MODEL = os.getenv("ASSISTANT_ID", "gpt-4")
openai.api_key = OPENAI_API_KEY

# --------------------- Налаштування шляху до Tesseract ---------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\ПК\брама-юа-бот\appp\app\tesseract\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Users\ПК\брама-юа-бот\appp\app\tesseract\tessdata"

# --------------------- Інші константи та глобальні змінні ---------------------
SYSTEM_INSTRUCTIONS = """Ви Асистент працюєте від неприбуткової організації Brama-UA e.V.

Відповідайте завжди на тій мові, на якій до Вас звернулись. Організація допомагає українцям у Німеччині інтегруватися в суспільство.
Ассистент також шукає інформацію на наступних ресурсах для надання актуальних консультацій:
- [Jobcenter Digital](https://www.jobcenter-digital.de)
- [Agentur für Arbeit](https://www.arbeitsagentur.de)
- [Gründenplattform.de](https://gruendenplattform.de)

Ассистент повинен завжди відповідати користувачам на тій мові, на якій до нього звертаються.

### Алгоритм пошуку інформації:
1. Визначення теми запиту: Ассистент аналізує ключові слова та тему запиту користувача. Якщо потрібно — ставить уточнюючі запитання.
2. Формулювання пошукового запиту: Створює релевантний пошуковий запит із зазначенням ключових слів та уточнень.
3. Вибір джерела: Обирає ресурс для пошуку інформації (Jobcenter Digital, Agentur für Arbeit, Gründenplattform.de).
4. Пошук інформації: Використовує внутрішній інструмент для пошуку на зазначених сайтах.
5. Обробка результатів: Відбирає найбільш релевантні дані (посилання на сторінки, текстові витяги, файли чи документи).

### Формат надання результатів:
- Посилання: Пряме посилання на відповідну сторінку з коротким описом.
- Текстовий витяг: Короткий текст із основною інформацією.
- Файл або документ: Якщо знайдено релевантний файл, надається його посилання для завантаження.
- Рекомендації: У разі необхідності, додаткові пояснення чи пропозиції щодо подальших дій.

### Додаткові функції:
1. Пошук і завантаження PDF-файлів:
   - Ассистент може шукати необхідні бланки чи документи у форматі PDF.
   - Після пошуку файл надається користувачеві як посилання для завантаження або надсилається безпосередньо через Telegram.
2. Надсилання PDF-файлів:
   - За запитом користувача Ассистент може надіслати необхідний PDF-файл у Telegram як документ.
3. Обробка голосових повідомлень:
   - Ассистент приймає голосові повідомлення від користувачів через Telegram.
   - Використовує OpenAI Whisper API для перетворення голосу в текст.
   - Отриманий текст обробляється як звичайний запит, на який Асистент надає відповідь.
4. Обробка фото документу:
   - Ассистент приймає фото листа чи документа, аналізує зміст, пояснює на мові, якою звернулись, і дає поради згідно законодавства.
"""

# --------------------- Головний обробник ---------------------
async def universal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[INFO] Обробка повідомлення почалася.")
    chat_id = update.effective_chat.id

    if update.message.text:
        print("[INFO] Отримано текстове повідомлення.")
        user_msg = update.message.text
        await process_text_message(user_msg, chat_id, update, context)

    elif update.message.photo:
        print("[INFO] Отримано фото.")
        await update.message.reply_text("Обробка фото поки що не працює коректно. Надішліть, будь ласка, текст чи голосове повідомлення.")

    elif update.message.voice:
        print("[INFO] Отримано голосове повідомлення.")
        await process_voice_message(update, context)

    else:
        print("[INFO] Невідомий формат повідомлення.")
        await update.message.reply_text("Невідомий формат повідомлення. Надішліть текст або голосове повідомлення.")

# --------------------- Обробка текстових повідомлень ---------------------
async def process_text_message(user_msg, chat_id, update, context):
    print(f"[INFO] Обробка текстового повідомлення: {user_msg}")
    try:
        print("[INFO] Надсилання запиту до OpenAI.")
        response = openai.ChatCompletion.create(
            model=ASSISTANT_MODEL,
            messages=[{"role": "system", "content": SYSTEM_INSTRUCTIONS}, {"role": "user", "content": user_msg}],
            temperature=0.7
        )
        assistant_reply = response.choices[0].message.content
        print(f"[INFO] Отримано відповідь від OpenAI: {assistant_reply}")
        await update.message.reply_text(assistant_reply)

    except Exception as e:
        logger.error(f"Помилка OpenAI: {e}")
        print(f"[ERROR] Помилка OpenAI: {e}")
        await update.message.reply_text("Вибачте, сталася помилка при обробці вашого запиту.")

# --------------------- Обробка голосових повідомлень ---------------------
async def process_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[INFO] Початок обробки голосового повідомлення.")
    try:
        voice = update.message.voice
        file_id = voice.file_id
        new_file = await context.bot.get_file(file_id)
        file_data = await new_file.download_as_bytearray()

        audio_buffer = BytesIO(file_data)
        audio_buffer.name = "audio.ogg"

        print("[INFO] Використання Whisper для розпізнавання голосу.")
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=audio_buffer,
            language="uk"
        )
        text_result = transcript["text"]

        print(f"[INFO] Whisper успішно розпізнав текст: {text_result}")
        await process_text_message(text_result, update.effective_chat.id, update, context)

    except Exception as e:
        logger.error(f"Помилка при транскрипції голосу: {e}")
        print(f"[ERROR] Помилка транскрипції: {e}")
        await update.message.reply_text("Не вдалося розпізнати голосове повідомлення.")

# --------------------- Запуск бота ---------------------
def main():
    print("[INFO] Запуск бота.")
    if not TELEGRAM_TOKEN:
        raise ValueError("У .env не задано TELEGRAM_TOKEN")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(MessageHandler(filters.ALL, universal_handler))

    logger.info("Бот запущено... Натисніть Ctrl+C для зупинки.")
    print("[INFO] Бот запущено. Чекаємо на повідомлення.")
    application.run_polling()

if __name__ == "__main__":
    main()
