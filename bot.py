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

        # Перевірка, чи потрібно створити PDF
        if "створити PDF" in assistant_reply.lower():
            print("[INFO] Виявлено запит на створення PDF.")
            await generate_pdf_from_ai(assistant_reply, update)
        else:
            await update.message.reply_text(assistant_reply)

    except Exception as e:
        logger.error(f"Помилка OpenAI: {e}")
        print(f"[ERROR] Помилка OpenAI: {e}")
        await update.message.reply_text("Вибачте, сталася помилка при обробці вашого запиту.")

# --------------------- Створення PDF ---------------------
async def generate_pdf_from_ai(content, update):
    print("[INFO] Початок створення PDF.")
    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    c.drawString(50, 800, "Згенерований PDF:")

    # Розбиваємо текст на рядки для кращого форматування
    y_position = 780
    line_height = 12
    for line in content.split("\n"):
        c.drawString(50, y_position, line)
        y_position -= line_height
        if y_position < 50:  # Нова сторінка, якщо бракує місця
            c.showPage()
            y_position = 780

    c.save()
    pdf_buffer.seek(0)

    pdf_name = f"generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    print(f"[INFO] PDF створено: {pdf_name}")
    await update.message.reply_document(document=pdf_buffer, filename=pdf_name)

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
