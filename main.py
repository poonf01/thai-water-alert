import requests
import os
from datetime import datetime
import pytz
from bs4 import BeautifulSoup

# --- เพิ่ม Library ของ Selenium และ Stealth ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException
from selenium_stealth import stealth # <-- เพิ่ม Library ตัวใหม่

# --- ค่าคงที่และตัวแปรหลัก ---
SINGBURI_WATER_URL = "https://singburi.thaiwater.net/wl"
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"


def get_singburi_data(url):
    driver = None
    try:
        print("[1/6] กำลังตั้งค่า Chrome Options...")
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        print("[2/6] กำลังติดตั้งและเริ่มต้น WebDriver...")
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        
        # --- ใช้ Stealth เพื่อพรางตัว ---
        print("[3/6] กำลังใช้ Stealth เพื่อพรางตัว...")
        stealth(driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
                )
        print("✅ พรางตัวสำเร็จ")

        print(f"[4/6] กำลังเปิด URL: {url}...")
        driver.get(url)
        print("✅ เปิด URL สำเร็จ")
        
        print("[5/6] กำลังรอให้ตารางข้อมูลปรากฏ (สูงสุด 60 วินาที)...")
        wait = WebDriverWait(driver, 60) # เพิ่มเวลารอ element เป็น 60 วินาที
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "tbody > tr")))
        print("✅ พบตารางข้อมูลแล้ว")

        print("[6/6] กำลังดึงข้อมูล HTML และประมวลผล...")
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, 'html.parser')

        rows = soup.find_all("tr")
        for row in rows:
            station_header = row.find("th")
            if station_header and "อินทร์บุรี" in station_header.get_text(strip=True):
                print("✅ พบข้อมูลของ 'อินทร์บุรี'")
                tds = row.find_all("td")
                
                if len(tds) > 1 and tds[1].text.strip():
                    level_str = tds[1].text.strip()
                    water_level = float(level_str)
                    print(f"ระดับน้ำอินทร์บุรีที่ดึงได้ = {water_level} ม.รทก.")
                    return water_level
        
        print("❌ ไม่พบข้อมูลของ 'อินทร์บุรี' ในตาราง")
        return None

    except TimeoutException as te:
        print(f"❌ เกิดข้อผิดพลาด Timeout: {te}")
        return None
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")
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
    except FileNotFoundError:
        return 1000
    except Exception:
        return 1000

def analyze_and_create_message(inburi_level, dam_discharge):
    if inburi_level is None:
        return "เกิดข้อผิดพลาด: ไม่สามารถดึงข้อมูลระดับน้ำอินทร์บุรีได้ กรุณาตรวจสอบเว็บไซต์ singburi.thaiwater.net หรือตรวจสอบ Log การทำงานล่าสุด"

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
    print("===== เริ่มการทำงาน v8.0 (Stealth Mode) =====")
    inburi_level = get_singburi_data(SINGBURI_WATER_URL)
    dam_discharge = get_dam_discharge_from_file()
    final_message = analyze_and_create_message(inburi_level, dam_discharge)
    print("\n--- ข้อความที่จะส่ง ---")
    print(final_message)
    print("-------------------------\n")
    send_line_broadcast(final_message)
    print("===== การทำงานเสร็จสิ้น =====")
