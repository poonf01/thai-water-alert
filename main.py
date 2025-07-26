import requests
import os
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- ค่าคงที่ ---
SINGBURI_WATER_URL = "https://singburi.thaiwater.net/wl"
DISCHARGE_URL = "https://tiwrm.hii.or.th/DATA/REPORT/php/chart/chaopraya/small/chaopraya.php"
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"


# --- ดึงระดับน้ำอินทร์บุรี ---
def get_singburi_data(url):
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        driver.set_page_load_timeout(180)
        driver.get(url)

        wait = WebDriverWait(driver, 60)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody > tr")))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        rows = soup.find_all("tr")

        for row in rows:
            station_header = row.find("th")
            if station_header and "อินทร์บุรี" in station_header.get_text(strip=True):
                tds = row.find_all("td")
                if len(tds) > 1:
                    level_str = tds[1].text.strip()
                    return float(level_str)
        return None
    except Exception as e:
        print(f"❌ ERROR: get_singburi_data: {e}")
        return None
    finally:
        if driver:
            driver.quit()


# --- ดึงข้อมูล discharge จากเว็บ HII ---
def fetch_chao_phraya_dam_discharge():
    try:
        res = requests.get(DISCHARGE_URL, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        strong_tags = soup.find_all("strong")

        for tag in strong_tags:
            if "ท้ายเขื่อนเจ้าพระยา" in tag.text:
                table = tag.find_parent("table")
                if table:
                    red_text = table.find("span", class_="text_red")
                    if red_text and "cms" in red_text.text:
                        value_text = red_text.text.replace("cms", "").strip()
                        return float(value_text)
        return None
    except Exception as e:
        print(f"❌ ERROR: fetch_chao_phraya_dam_discharge: {e}")
        return None


# --- วิเคราะห์ข้อมูลและสร้างข้อความแจ้งเตือน ---
def analyze_and_create_message(inburi_level, dam_discharge):
    if inburi_level is None or dam_discharge is None:
        return "เกิดข้อผิดพลาด: ไม่สามารถดึงข้อมูลได้ครบ กรุณาตรวจสอบระบบ"

    bank_height = 13.0
    distance_to_bank = bank_height - inburi_level

    if dam_discharge > 2400 or distance_to_bank < 1.0:
        status_emoji = "🟥"
        status_title = "‼️ ประกาศเตือนภัยระดับสูงสุด ‼️"
        recommendation = """คำแนะนำ:\n1. เตรียมพร้อมอพยพหากอยู่ในพื้นที่เสี่ยง\n2. ขนย้ายทรัพย์สินขึ้นที่สูงโดยด่วน\n3. งดใช้เส้นทางสัญจรริมแม่น้ำ"""
    elif dam_discharge > 1800 or distance_to_bank < 2.0:
        status_emoji = "🟨"
        status_title = "‼️ ประกาศเฝ้าระวัง ‼️"
        recommendation = """คำแนะนำ:\n1. บ้านเรือนริมตลิ่งนอกคันกั้นน้ำ ให้เริ่มขนของขึ้นที่สูง\n2. ติดตามสถานการณ์อย่างใกล้ชิด"""
    else:
        status_emoji = "🟩"
        status_title = "สถานะปกติ"
        recommendation = "สถานการณ์น้ำยังปกติ ใช้ชีวิตได้ตามปกติครับ"

    now = datetime.now(pytz.timezone('Asia/Bangkok'))
    message = (
        f"{status_emoji} {status_title}\n"
        f"รายงานสถานการณ์น้ำเจ้าพระยา อ.อินทร์บุรี\n"
        f"ประจำวันที่: {now.strftime('%d/%m/%Y %H:%M')} น.\n\n"
        f"• ระดับน้ำ (อินทร์บุรี): {inburi_level:.2f} ม.รทก.\n"
        f"  (ต่ำกว่าตลิ่งประมาณ {distance_to_bank:.2f} ม.)\n"
        f"• เขื่อนเจ้าพระยา (ข้อมูลอ้างอิง): {dam_discharge:,.0f} ลบ.ม./วินาที\n\n"
        f"{recommendation}"
    )
    return message


# --- ส่งข้อความ Broadcast LINE ---
def send_line_broadcast(message):
    if not LINE_TOKEN:
        print("❌ ไม่พบ LINE_CHANNEL_ACCESS_TOKEN!")
        return
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    payload = {
        "messages": [{"type": "text", "text": message}]
    }
    try:
        res = requests.post(LINE_API_URL, headers=headers, json=payload, timeout=10)
        res.raise_for_status()
        print("✅ ส่งข้อความ Broadcast สำเร็จ!")
    except Exception as e:
        print(f"❌ ERROR: LINE Broadcast: {e}")


# --- Main ---
if __name__ == "__main__":
    print("=== เริ่มการทำงานระบบแจ้งเตือนน้ำอินทร์บุรี (Full Version) ===")
    inburi_level = get_singburi_data(SINGBURI_WATER_URL)
    dam_discharge = fetch_chao_phraya_dam_discharge() or 1000  # fallback if failed
    final_message = analyze_and_create_message(inburi_level, dam_discharge)

    print("\n📤 ข้อความที่จะแจ้งเตือน:")
    print(final_message)
    print("\n🚀 ส่งข้อความไปยัง LINE...")
    send_line_broadcast(final_message)
    print("✅ เสร็จสิ้นการทำงาน")
