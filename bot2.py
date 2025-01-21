import os
import openai
import pytesseract
import requests
import cv2
import numpy as np

from io import BytesIO
from PIL import Image
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
ASSISTANT_MODEL = os.getenv("ASSISTANT_ID", "gpt-3.5-turbo")
openai.api_key = OPENAI_API_KEY
os.environ["TESSDATA_PREFIX"] = r"C:\\Users\\ПК\\брама-юа-бот\\appp\\app\\tesseract\\tessdata"


# --------------------- Налаштування шляху до Tesseract ---------------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\ПК\брама-юа-бот\appp\app\tesseract\tesseract.exe"

# --------------------- Інші константи та глобальні змінні ---------------------
PDF_FOLDER = "pdf_files"
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

user_history = {}

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
        await handle_photo_message(update, context)

    elif update.message.voice:
        print("[INFO] Отримано голосове повідомлення.")
        await handle_voice_message(update, context)

    else:
        print("[INFO] Невідомий формат повідомлення.")
        await update.message.reply_text("Невідомий формат повідомлення. Надішліть текст, фото або голосове повідомлення.")

# --------------------- Обробка текстових повідомлень ---------------------
async def process_text_message(user_msg, chat_id, update, context):
    print(f"[INFO] Обробка текстового повідомлення: {user_msg}")
    global user_history
    if chat_id not in user_history:
        user_history[chat_id] = []

    user_history[chat_id].append({"role": "user", "content": user_msg})

    messages = [{"role": "system", "content": SYSTEM_INSTRUCTIONS}]
    messages += user_history[chat_id]

    try:
        print("[INFO] Надсилання запиту до OpenAI.")
        response = openai.ChatCompletion.create(
            model=ASSISTANT_MODEL,
            messages=messages,
            temperature=0.7
        )
        assistant_reply = response.choices[0].message.content

        print(f"[INFO] Отримано відповідь від OpenAI: {assistant_reply}")

        if "PDF" in assistant_reply.upper():
            print("[INFO] Виявлено запит, пов'язаний із PDF.")
            if "створити" in user_msg.lower():
                await createpdf_from_text(user_msg, update)
            elif "знайти" in user_msg.lower():
                await findpdf_command(user_msg, update)
            else:
                await update.message.reply_text("Не зрозуміло, що робити з PDF. Спробуйте уточнити.")
        else:
            await update.message.reply_text(assistant_reply)

    except Exception as e:
        logger.error(f"Помилка OpenAI: {e}")
        print(f"[ERROR] Помилка OpenAI: {e}")
        await update.message.reply_text("Вибачте, сталася помилка при обробці вашого запиту.")

# --------------------- Обробка фото ---------------------
from io import BytesIO
from PIL import Image
import pytesseract
from telegram import Update
from telegram.ext import ContextTypes

# --------------------- Обробка фото ---------------------
from PIL import ImageOps, ImageEnhance

def decode_tesseract_output(raw_text):
    """Helper function to decode Tesseract output with multiple encodings"""
    encodings = ['utf-8', 'latin1', 'cp1251', 'iso-8859-1', 'windows-1252']
    
    for encoding in encodings:
        try:
            # Try to decode bytes using current encoding
            if isinstance(raw_text, bytes):
                return raw_text.decode(encoding)
            # Try to encode and then decode if string
            return raw_text.encode(encoding).decode('utf-8')
        except UnicodeError:
            continue
    
    # If all encodings fail, try to clean the string
    return ''.join(char for char in raw_text if ord(char) < 128)

# --------------------- Обробка фото ---------------------
def decode_tesseract_output(raw_text):
    """Допоміжна функція для декодування результату Tesseract"""
    encodings = ['utf-8', 'latin1', 'cp1251', 'iso-8859-1', 'windows-1252']
    for encoding in encodings:
        try:
            if isinstance(raw_text, bytes):
                return raw_text.decode(encoding)
            return raw_text.encode(encoding).decode('utf-8')
        except UnicodeError:
            continue
    return ''.join(char for char in raw_text if ord(char) < 128)

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[INFO] Початок обробки фото.")
    try:
        photo = update.message.photo[-1]
        file_id = photo.file_id
        new_file = await context.bot.get_file(file_id)
        file_data = await new_file.download_as_bytearray()

        # Перетворення у зображення та попередня обробка
        img_buffer = BytesIO(file_data)
        img = Image.open(img_buffer)
        img = img.convert("L")  # Градація сірого
        img = ImageOps.autocontrast(img)  # Автоматичний контраст
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2)  # Підвищення контрасту

        # OCR з кількома режимами PSM
        psm_modes = [6, 3, 4]
        text_result = None
        for psm in psm_modes:
            try:
                print(f"[INFO] Спроба OCR з PSM режимом {psm}")
                raw_result = pytesseract.image_to_string(img, lang="deu", config=f"--psm {psm} --oem 3")
                text_result = decode_tesseract_output(raw_result)
                if text_result.strip():
                    print(f"[INFO] Успішно розпізнано текст з PSM={psm}")
                    break
            except Exception as e:
                print(f"[WARNING] Помилка з PSM={psm}: {e}")
        
        if not text_result or not text_result.strip():
            print("[WARNING] Не вдалося розпізнати текст.")
            await update.message.reply_text(
                "Не вдалося розпізнати текст. Спробуйте:\n"
                "1. Використати чіткіше фото\n"
                "2. Збільшити контрастність тексту\n"
                "3. Уникати тіней або відблисків"
            )
            return

        # Виведення результатів
        text_result = ' '.join(text_result.split())  # Очищення від зайвих пробілів
        print(f"[INFO] Фінальний результат OCR ({len(text_result)} символів):\n{text_result}")
        await update.message.reply_text(f"Розпізнаний текст (німецькою):\n\n{text_result}")

    except Exception as e:
        logger.error(f"Помилка при обробці фото: {e}")
        print(f"[ERROR] Помилка: {e}")
        await update.message.reply_text("Виникла помилка при обробці зображення.")

# --------------------- Пошук PDF ---------------------
async def findpdf_command(query, update):
    print(f"[INFO] Початок пошуку PDF для запиту: {query}")
    found_files = []
    if os.path.exists(PDF_FOLDER):
        for f in os.listdir(PDF_FOLDER):
            if f.lower().endswith(".pdf") and query.lower() in f.lower():
                found_files.append(f)

    if not found_files:
        print("[INFO] PDF не знайдено.")
        await update.message.reply_text(f"Не знайдено PDF із назвою, що містить: {query}")
    else:
        for f in found_files:
            print(f"[INFO] Знайдено PDF: {f}")
            file_path = os.path.join(PDF_FOLDER, f)
            await update.message.reply_text(f"Знайдено файл: {f}\nНадсилаю...")
            with open(file_path, 'rb') as doc:
                await update.message.reply_document(document=doc)

# --------------------- Обробка голосових повідомлень (Whisper) ---------------------

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробка голосового повідомлення.
    1. Завантажуємо файл .oga (стандарт Telegram).
    2. Надсилаємо в OpenAI Whisper API для транскрипту.
    3. Додаємо транскрибований текст до handle_text_message.
    """
    voice = update.message.voice
    file_id = voice.file_id
    new_file = await context.bot.get_file(file_id)
    file_data = await new_file.download_as_bytearray()

    try:
        # Зберігаємо у тимчасовий буфер
        audio_buffer = BytesIO(file_data)
        audio_buffer.name = "audio.ogg"

        # Використовуємо Whisper API
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=audio_buffer,
            language="uk"  # Або "en", "de" тощо
        )
        text_result = transcript["text"]

        await update.message.reply_text(f"Розпізнаний текст: {text_result}")

        # Далі обробляємо цей текст, як звичайне текстове повідомлення
        update.message.text = text_result
        await handle_text_message(update, context)

    except Exception as e:
        logger.error(f"Помилка при транскрипції голосу: {e}")
        await update.message.reply_text("Вибачте, не вдалося розпізнати голос.")


# --------------------- Створення PDF ---------------------
async def createpdf_from_text(user_text, update):
    print(f"[INFO] Початок створення PDF з тексту: {user_text}")
    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    c.drawString(50, 800, "Створений PDF-файл:")
    c.drawString(50, 780, user_text)
    c.showPage()
    c.save()
    pdf_buffer.seek(0)

    pdf_name = f"created_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    print(f"[INFO] PDF створено: {pdf_name}")
    await update.message.reply_document(document=pdf_buffer, filename=pdf_name)

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
