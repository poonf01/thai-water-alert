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
    """
    ดึงข้อมูลจากเว็บ singburi.thaiwater.net
    คืนค่า: (ระดับน้ำ, ระดับตลิ่ง) หรือ (None, None) หากล้มเหลว
    """
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        driver.set_page_load_timeout(180)
        driver.get(url)

        # รอจนกว่าตารางจะโหลดเสร็จ
        wait = WebDriverWait(driver, 60)
        # เราจะรอให้ตารางทั้งอันโหลดเสร็จ โดยหาจาก id ของตารางที่เห็นใน DevTools
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[aria-labelledby='waterLevel'] table")))

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # ค้นหาตารางหลักที่มีข้อมูลระดับน้ำโดยตรง
        water_table = soup.find("div", attrs={"aria-labelledby": "waterLevel"})
        if not water_table:
            print("⚠️ ไม่พบตารางข้อมูลระดับน้ำหลัก (div[aria-labelledby='waterLevel'])")
            return None, None
            
        rows = water_table.find_all("tr")

        for row in rows:
            station_header = row.find("th")
            if station_header and "อินทร์บุรี" in station_header.get_text(strip=True):
                tds = row.find_all("td")
                # จาก HTML ใหม่ เราต้องการข้อมูลจาก <td> ที่ 2 และ 3
                if len(tds) > 2:
                    level_str = tds[1].text.strip() # ระดับน้ำ (ม.รทก.)
                    bank_level_str = tds[2].text.strip() # ระดับตลิ่ง
                    print(f"✅ พบข้อมูลอินทร์บุรี: ระดับน้ำ={level_str}, ระดับตลิ่ง={bank_level_str}")
                    return float(level_str), float(bank_level_str)
                    
        print("⚠️ ไม่พบข้อมูลสถานี 'อินทร์บุรี' ในตาราง")
        return None, None
    except Exception as e:
        print(f"❌ ERROR: get_singburi_data: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()


# --- ดึงข้อมูล discharge จากเว็บ HII ---
def fetch_chao_phraya_dam_discharge():
    # TODO: หากสคริปต์ไม่ทำงาน ให้ตรวจสอบ Selector ในฟังก์ชันนี้
    # โดยการเปิดเว็บ DISCHARGE_URL แล้วเช็คโครงสร้าง HTML
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
        print("⚠️ ไม่พบข้อมูล 'ท้ายเขื่อนเจ้าพระยา' ในหน้าเว็บ")
        return None
    except Exception as e:
        print(f"❌ ERROR: fetch_chao_phraya_dam_discharge: {e}")
        return None


# --- วิเคราะห์ข้อมูลและสร้างข้อความแจ้งเตือน ---
def analyze_and_create_message(inburi_level, dam_discharge, bank_height):
    distance_to_bank = bank_height - inburi_level

    if dam_discharge > 2400 or distance_to_bank < 1.0:
        status_emoji = "🟥"
        status_title = "‼️ ประกาศเตือนภัยระดับสูงสุด ‼️"
        recommendation = "คำแนะนำ:\n1. เตรียมพร้อมอพยพหากอยู่ในพื้นที่เสี่ยง\n2. ขนย้ายทรัพย์สินขึ้นที่สูงโดยด่วน\n3. งดใช้เส้นทางสัญจรริมแม่น้ำ"
    elif dam_discharge > 1800 or distance_to_bank < 2.0:
        status_emoji = "🟨"
        status_title = "‼️ ประกาศเฝ้าระวัง ‼️"
        recommendation = "คำแนะนำ:\n1. บ้านเรือนริมตลิ่งนอกคันกั้นน้ำ ให้เริ่มขนของขึ้นที่สูง\n2. ติดตามสถานการณ์อย่างใกล้ชิด"
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
        f"  (ระดับตลิ่ง: {bank_height:.2f} ม.รทก.)\n"
        f"• เขื่อนเจ้าพระยา (ข้อมูลอ้างอิง): {dam_discharge:,.0f} ลบ.ม./วินาที\n\n"
        f"{recommendation}"
    )
    return message


# --- สร้างข้อความแจ้งเตือนข้อผิดพลาด ---
def create_error_message(inburi_status, discharge_status):
    now = datetime.now(pytz.timezone('Asia/Bangkok'))
    message = (
        f"⚙️❌ เกิดข้อผิดพลาดในการดึงข้อมูล ❌⚙️\n"
        f"เวลา: {now.strftime('%d/%m/%Y %H:%M')} น.\n\n"
        f"• สถานะข้อมูลระดับน้ำอินทร์บุรี: {inburi_status}\n"
        f"• สถานะข้อมูลเขื่อนเจ้าพระยา: {discharge_status}\n\n"
        f"กรุณาตรวจสอบ Log บน GitHub Actions เพื่อดูรายละเอียดข้อผิดพลาดครับ"
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
    print("=== เริ่มการทำงานระบบแจ้งเตือนน้ำอินทร์บุรี ===")
    
    print("1. กำลังดึงข้อมูลระดับน้ำ อ.อินทร์บุรี...")
    inburi_level, bank_level = get_singburi_data(SINGBURI_WATER_URL)
    
    print("2. กำลังดึงข้อมูลระบายน้ำเขื่อนเจ้าพระยา...")
    dam_discharge = fetch_chao_phraya_dam_discharge()

    print("\n--- สรุปผลการดึงข้อมูล ---")
    print(f"ระดับน้ำอินทร์บุรี: {inburi_level}, ระดับตลิ่ง: {bank_level}")
    print(f"เขื่อนเจ้าพระยา: {dam_discharge}")
    print("--------------------------\n")

    final_message = ""
    # ตรวจสอบว่าดึงข้อมูลที่จำเป็นสำเร็จทั้งหมดหรือไม่
    if inburi_level is not None and bank_level is not None and dam_discharge is not None:
        print("✅ ดึงข้อมูลสำเร็จทั้งหมด กำลังสร้างข้อความปกติ...")
        final_message = analyze_and_create_message(inburi_level, dam_discharge, bank_level)
    else:
        print("❌ ดึงข้อมูลไม่สำเร็จอย่างน้อย 1 รายการ กำลังสร้างข้อความแจ้งเตือนข้อผิดพลาด...")
        inburi_status = f"สำเร็จ (ระดับน้ำ={inburi_level}, ตลิ่ง={bank_level})" if inburi_level is not None else "ล้มเหลว"
        discharge_status = f"สำเร็จ ({dam_discharge})" if dam_discharge is not None else "ล้มเหลว"
        final_message = create_error_message(inburi_status, discharge_status)

    print("\n📤 ข้อความที่จะแจ้งเตือน:")
    print(final_message)
    print("\n🚀 ส่งข้อความไปยัง LINE...")
    send_line_broadcast(final_message)
    print("✅ เสร็จสิ้นการทำงาน")
