import requests
import os
from datetime import datetime
import pytz
from bs4 import BeautifulSoup

# --- ไม่ต้องใช้ selenium-stealth ในเวอร์ชันนี้ ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- ค่าคงที่และตัวแปรหลัก ---
SINGBURI_WATER_URL = "https://singburi.thaiwater.net/wl"
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"


def get_singburi_data(url):
    """
    (v11 - Simplified) ทดลองดึงข้อมูลด้วย Selenium ที่มีการตั้งค่าน้อยที่สุด
    """
    driver = None
    try:
        print("กำลังตั้งค่า Chrome Options (Simplified)...")
        options = webdriver.ChromeOptions()
        # เหลือไว้เฉพาะ options ที่จำเป็นสำหรับ GitHub Actions
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        print("กำลังติดตั้งและเริ่มต้น WebDriver...")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        
        print("กำลังตั้งค่า Page Load Timeout เป็น 180 วินาที...")
        driver.set_page_load_timeout(180) # ให้เวลารอโหลดหน้าเว็บ 3 นาที
        
        print(f"กำลังเปิด URL: {url}...")
        driver.get(url)
        
        print("กำลังรอให้ตารางข้อมูลปรากฏ...")
        wait = WebDriverWait(driver, 60)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody > tr")))
        
        print("กำลังดึงข้อมูล HTML...")
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, 'html.parser')

        rows = soup.find_all("tr")
        for row in rows:
            station_header = row.find("th")
            if station_header and "อินทร์บุรี" in station_header.get_text(strip=True):
                tds = row.find_all("td")
                if len(tds) > 1 and tds[1].text.strip():
                    level_str = tds[1].text.strip()
                    water_level = float(level_str)
                    return water_level
        
        return None

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในฟังก์ชัน get_singburi_data: {e}")
        return None
    finally:
        if driver:
            print("กำลังปิด WebDriver...")
            driver.quit()

#
# --- ส่วนที่เหลือของไฟล์เหมือนเดิม ---
#
def get_dam_discharge_from_file():
    try:
        with open('dam_data.txt', 'r') as f:
            discharge_rate = float(f.read().strip())
        return discharge_rate
    except Exception:
        return 1000

def analyze_and_create_message(inburi_level, dam_discharge):
    if inburi_level is None:
        return "เกิดข้อผิดพลาด: ไม่สามารถดึงข้อมูลระดับน้ำอินทร์บุรีได้ กรุณาตรวจสอบ Log การทำงานล่าสุด"

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

    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)

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

def send_line_broadcast(message):
    if not LINE_TOKEN:
        print("❌ ไม่พบ LINE_CHANNEL_ACCESS_TOKEN!")
        return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"messages": [{"type": "text", "text": message}]}
    try:
        response = requests.post(LINE_API_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ ส่งข้อความ Broadcast สำเร็จ!")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการส่ง LINE Broadcast: {e}")


if __name__ == "__main__":
    print("===== เริ่มการทำงาน v11.0 (Simplified) =====")
    inburi_level = get_singburi_data(SINGBURI_WATER_URL)
    dam_discharge = get_dam_discharge_from_file()
    final_message = analyze_and_create_message(inburi_level, dam_discharge)
    print("\n--- ข้อความที่จะส่ง ---")
    print(final_message)
    print("-------------------------\n")
    send_line_broadcast(final_message)
    print("===== การทำงานเสร็จสิ้น =====")
