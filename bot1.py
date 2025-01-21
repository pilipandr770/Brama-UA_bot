
import os
import openai
import pytesseract
import requests

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
ASSISTANT_MODEL = os.getenv("ASSISTANT_ID", "gpt-3.5-turbo")  # Наприклад "gpt-4"
openai.api_key = OPENAI_API_KEY

# --------------------- Налаштування шляху до Tesseract ---------------------
# Припустимо, що ви скопіювали портативний Tesseract у папку:
# C:\Users\ПК\брама-юа-бот\appp\app\tesseract\tesseract.exe
# Переконайтеся, що шлях правильний та файл існує
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\ПК\брама-юа-бот\appp\app\tesseract\tesseract.exe"

# Якщо Tesseract.exe лежить у іншому місці, змініть шлях у рядку вище.


# --------------------- Інші константи та глобальні змінні ---------------------

# Папка для PDF-файлів (де шукаємо готові pdf)
PDF_FOLDER = "pdf_files"

# Системне повідомлення (довгі інструкції)
SYSTEM_INSTRUCTIONS = """Ви  Асистент працюєте від неприбуткової організації Brama-UA e.V.

Відповідайте завжди на тій мові, на якій до Вас звернулись. Організація допомагає українцям у Німеччині інтегруватися в суспільство. Ассистент має доступ до файлів у векторному магазині та повинен консультувати тих, хто звертається за консультацією чи допомогою.

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

# Історія спілкування з користувачами
user_history = {}


# --------------------- Обробники команд ---------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Вітаю! Я Асистент Brama-UA. Напишіть чи надішліть щось, і я спробую допомогти."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Доступні команди:\n"
        "/start — почати роботу\n"
        "/help — показати це повідомлення\n"
        "/findpdf <ім'я файлу> — знайти та надіслати PDF із локальної папки\n"
        "/createpdf <текст> — створити PDF з вашим текстом і надіслати\n"
        "(Надішліть голосове повідомлення, щоб я його розпізнав; фото, щоб я витягнув текст.)"
    )
    await update.message.reply_text(help_text)


# --------------------- Обробка текстових повідомлень ---------------------

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка звичайних текстових повідомлень (без команд)."""
    chat_id = update.effective_chat.id
    user_msg = update.message.text

    if chat_id not in user_history:
        user_history[chat_id] = []

    # Додаємо повідомлення користувача
    user_history[chat_id].append({"role": "user", "content": user_msg})

    # Формуємо список для ChatCompletion
    messages = [{"role": "system", "content": SYSTEM_INSTRUCTIONS}]
    messages += user_history[chat_id]

    try:
        response = openai.ChatCompletion.create(
            model=ASSISTANT_MODEL,
            messages=messages,
            temperature=0.7
        )
        assistant_reply = response.choices[0].message.content
    except Exception as e:
        logger.error(f"Помилка OpenAI: {e}")
        assistant_reply = "Вибачте, сталася помилка при отриманні відповіді."

    # Додаємо відповідь асистента до історії
    user_history[chat_id].append({"role": "assistant", "content": assistant_reply})

    await update.message.reply_text(assistant_reply)


# --------------------- Пошук і відправлення PDF ---------------------

async def findpdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пошук PDF-файлу за назвою у папці PDF_FOLDER та надсилання."""
    if not context.args:
        await update.message.reply_text("Синтаксис: /findpdf <назва файлу>")
        return
    filename_query = context.args[0]

    found_files = []
    if os.path.exists(PDF_FOLDER):
        for f in os.listdir(PDF_FOLDER):
            if f.lower().endswith(".pdf") and filename_query.lower() in f.lower():
                found_files.append(f)
    
    if not found_files:
        await update.message.reply_text(
            f"Не знайдено PDF із назвою, що містить: {filename_query}"
        )
    else:
        for f in found_files:
            file_path = os.path.join(PDF_FOLDER, f)
            await update.message.reply_text(f"Знайдено файл: {f}\nНадсилаю...")
            try:
                with open(file_path, 'rb') as doc:
                    await update.message.reply_document(document=doc)
            except Exception as e:
                await update.message.reply_text(f"Помилка при відправці файлу {f}: {e}")


# --------------------- Створення PDF ---------------------

async def createpdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Створення PDF з указаним текстом та надсилання."""
    user_text = " ".join(context.args)  # все, що йде після команди
    if not user_text.strip():
        await update.message.reply_text("Синтаксис: /createpdf <текст для PDF>")
        return

    # Створюємо PDF у пам'яті
    pdf_buffer = BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    c.drawString(50, 800, "Створений PDF-файл:")
    c.drawString(50, 780, user_text)
    c.showPage()
    c.save()
    pdf_buffer.seek(0)

    # Відправляємо PDF як документ
    pdf_name = f"created_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    await update.message.reply_document(document=pdf_buffer, filename=pdf_name)


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


# --------------------- Обробка фото (OCR з pytesseract) ---------------------

async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обробка фото документа.
    Використовуємо pytesseract (локальний OCR).
    Якщо у вас був би GPT-4 with Vision, тоді був би інший механізм.
    """
    photos = update.message.photo
    if not photos:
        return

    photo = photos[-1]  # Беремо найбільшу за розміром
    file_id = photo.file_id
    new_file = await context.bot.get_file(file_id)
    file_data = await new_file.download_as_bytearray()

    try:
        img_buffer = BytesIO(file_data)
        img = Image.open(img_buffer)

        # Вказуємо мови (українська + англійська)
        text_result = pytesseract.image_to_string(img, lang="ukr+eng")

        if not text_result.strip():
            await update.message.reply_text("Не вдалося розпізнати текст на зображенні.")
        else:
            # Виводимо розпізнаний текст
            await update.message.reply_text(f"Розпізнаний текст:\n{text_result}")

            # Якщо треба — передаємо цей текст як запит у GPT
            update.message.text = text_result
            await handle_text_message(update, context)

    except Exception as e:
        logger.error(f"Помилка при OCR фото: {e}")
        await update.message.reply_text("Не вдалося обробити це зображення.")


# --------------------- Запуск бота ---------------------

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("У .env не задано TELEGRAM_TOKEN")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Команди
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("findpdf", findpdf_command))
    application.add_handler(CommandHandler("createpdf", createpdf_command))

    # Обробка текстових повідомлень
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # Обробка голосових повідомлень (Whisper)
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    # Обробка фото (OCR)
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))

    logger.info("Бот запущено... Натисніть Ctrl+C для зупинки.")
    application.run_polling()

if __name__ == "__main__":
    main()
