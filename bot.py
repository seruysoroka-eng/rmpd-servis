# bot.py
# pip install -r requirements.txt
import os, time, json, re, base64
from io import BytesIO
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import telegram
from telegram.ext import Updater, CommandHandler

URL = "https://puesc.gov.pl/web/guest/uslugi/przewoz-towarow-objety-monitorowaniem/rmpd-406?systemName=SENT&formName=1000972"
TELE_TOKEN   = os.getenv("TELE_TOKEN")   # @BotFather
TELE_CHAT_ID = os.getenv("TELE_CHAT_ID") # ваш chat_id
SCREEN_EVERY = 20 * 60                   # загальний скрін кожні 20 хв
HISTORY_DIR  = "history"                 # для історії заявок
os.makedirs(HISTORY_DIR, exist_ok=True)

options = webdriver.ChromeOptions()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=options)

def crop_center(img_bytes, save_path):
    img = Image.open(img_bytes)
    w, h = img.size
    box = (0, 200, w, h-150)
    img.crop(box).save(save_path, quality=85)

def parse_one_number(rmpd: str, auto: str, tracker: str):
    """вводимо 3 поля і парсимо відповідь"""
    driver.get(URL)
    # 1. номер заявки
    inp1 = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='numerWniosku']")))
    inp1.clear(); inp1.send_keys(rmpd)
    # 2. номер авто
    inp2 = driver.find_element(By.CSS_SELECTOR, "input[name='numerRejestracyjny']")
    inp2.clear(); inp2.send_keys(auto)
    # 3. номер трекера
    inp3 = driver.find_element(By.CSS_SELECTOR, "input[name='sentId']")
    inp3.clear(); inp3.send_keys(tracker)
    # натискаємо Szukaj
    btn = driver.find_element(By.XPATH, "//button[text()='Szukaj']")
    btn.click()
    time.sleep(5)  # чекаємо таблицю
    png = driver.get_screenshot_as_png()
    key = f"{rmpd}_{auto}_{tracker}".replace("/", "_").replace(" ", "_")
    crop_center(BytesIO(png), f"{HISTORY_DIR}/{key}.jpg")
    # парсинг статусу
    if b"Zrealizowano" in png:   status = "✅ Zrealizowano"
    elif b"Odmowa" in png:       status = "❌ Odmowa"
    else:                        status = "⏳ In progress"
    # історія
    hist_file = f"{HISTORY_DIR}/{key}.json"
    hist = [] if not os.path.exists(hist_file) else json.load(open(hist_file))
    hist.append({"ts": int(time.time()), "status": status})
    with open(hist_file, "w") as f:
        json.dump(hist, f, indent=2)
    return status, f"{HISTORY_DIR}/{key}.jpg"

def send_telegram(text, photo_path=None):
    bot = telegram.Bot(TELE_TOKEN)
    if photo_path:
        with open(photo_path, "rb") as f:
            bot.send_photo(chat_id=TELE_CHAT_ID, photo=f, caption=text)
    else:
        bot.send_message(chat_id=TELE_CHAT_ID, text=text)

def tele_track(update, context):
    """C. /track 406/2025/12345 AB123456 123456789"""
    if len(context.args) != 3:
        update.message.reply_text("❗ Використання: /track <RMPD> <AUTO> <TRACKER>\nПриклад: /track 406/2025/12345 AB123456 123456789")
        return
    rmpd, auto, tracker = context.args
    update.message.reply_text(f"🔍 Шукаю {rmpd} {auto} {tracker} ...")
    try:
        status, pic = parse_one_number(rmpd, auto, tracker)
        update.message.reply_text(f"📊 Статус: {status}")
        with open(pic, "rb") as f:
            update.message.reply_photo(photo=f)
    except Exception as e:
        update.message.reply_text(f"❌ Помилка: {e}")

def main():
    # загальний скрін (без номера) кожні 20 хв
    while True:
        try:
            driver.get(URL)
            time.sleep(5)
            png = driver.get_screenshot_as_png()
            crop_center(BytesIO(png), "screen.jpg")
            if b"Zrealizowano" in png:   status = "✅ Zrealizowano"
            elif b"Odmowa" in png:       status = "❌ Odmowa"
            else:                        status = "⏳ In progress"
            with open("status.json", "w") as f:
                f.write('{"status":"' + status + '","screen":"data:image/jpeg;base64,' +
                        base64.b64encode(open("screen.jpg", "rb").read()).decode() + '"}')
        except Exception as e:
            with open("error.log", "a") as f:
                f.write(time.ctime() + " " + str(e) + "\n")
        time.sleep(SCREEN_EVERY)

if __name__ == "__main__":
    # Telegram-команди в окремому потоці
    updater = Updater(TELE_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("track", tele_track))
    updater.start_polling(drop_pending_updates=True)
    # основний цикл – загальний моніторинг
    main()
