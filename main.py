# === START OF FILE: main.py ===
import os
import re
import json
import time
import random
import requests
import pytz
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# --- ส่วนของ Selenium ---
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("⚠️ ไม่ได้ติดตั้ง Selenium หรือ Webdriver Manager")


# --- ค่าคงที่ ---
SINGBURI_URL = "https://singburi.thaiwater.net/wl"
DISCHARGE_URL = 'https://tiwrm.hii.or.th/DATA/REPORT/php/chart/chaopraya/small/chaopraya.php'
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_GROUP_ID = os.environ.get('LINE_GROUP_ID')
LINE_PUSH_API_URL = "https://api.line.me/v2/bot/message/push"

# --- ฟังก์ชันสำหรับตั้งค่า Selenium Driver ---
def setup_driver():
    """ตั้งค่า Chrome Driver สำหรับทำงานแบบ Headless บน Server (เพิ่มประสิทธิภาพ)"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(60)
    driver.set_script_timeout(60)
    return driver

# -- อ่านข้อมูลย้อนหลังจาก Excel --
THAI_MONTHS = { 'มกราคม':1, 'กุมภาพันธ์':2, 'มีนาคม':3, 'เมษายน':4, 'พฤษภาคม':5, 'มิถุนายน':6, 'กรกฎาคม':7, 'สิงหาคม':8, 'กันยายน':9, 'ตุลาคม':10, 'พฤศจิกายน':11, 'ธันวาคม':12 }
def get_historical_from_excel(year_be: int) -> int | None:
    possible_paths = [f"data/ระดับน้ำปี{year_be}.xlsx", f"ระดับน้ำปี{year_be}.xlsx"]
    file_path = next((p for p in possible_paths if os.path.exists(p)), None)
    if file_path is None: print(f"⚠️ ไม่พบไฟล์ข้อมูลย้อนหลังปี {year_be}"); return None
    try:
        df = pd.read_excel(file_path)
        discharge_col = next((col for col in df.columns if any(k in str(col) for k in ['ลบ.ม.', 'discharge', 'ค่า'])), None)
        if discharge_col is None: return None
        df = df.rename(columns={discharge_col: 'discharge'})
        if 'เดือน' in df.columns and 'วันที่' in df.columns:
            df['month_num'], df['day_num'] = df['เดือน'].map(THAI_MONTHS), df['วันที่']
        elif 'วันที่' in df.columns:
            df['date'] = pd.to_datetime(df['วันที่'], errors='coerce'); df['month_num'], df['day_num'] = df['date'].dt.month, df['date'].dt.day
        else: return None
        now = datetime.now(pytz.timezone('Asia/Bangkok'))
        match = df[(df['day_num'] == now.day) & (df['month_num'] == now.month)]
        if not match.empty:
            val = match.iloc[0]['discharge']; val_int = int(str(val).replace(',', ''))
            print(f"✅ พบข้อมูลย้อนหลังสำหรับปี {year_be}: {val_int} ลบ.ม./วินาที (ไฟล์: {file_path})"); return val_int
        print(f"⚠️ ไม่พบข้อมูลสำหรับวันที่ {now.day}/{now.month} ในไฟล์ปี {year_be}"); return None
    except Exception as e:
        print(f"❌ ERROR: ไม่สามารถโหลดข้อมูลย้อนหลังจาก Excel ได้ ({file_path}): {e}"); return None

# --- [แก้ไขครั้งสุดท้าย] ดึงระดับน้ำอินทร์บุรี (ใช้วิธีค้นหาที่แม่นยำที่สุด) ---
def get_inburi_data(url: str):
    if not SELENIUM_AVAILABLE: return None, None
    driver = setup_driver()
    try:
        try:
            driver.get(url)
        except TimeoutException:
            print("⚠️ ERROR: หน้าเว็บอินทร์บุรีโหลดไม่เสร็จในเวลาที่กำหนด"); return None, None
            
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'อินทร์บุรี')]")))
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        
        # 1. ค้นหา <th> ที่มี scope="row" และข้อความ "อินทร์บุรี"
        header_cell = soup.find('th', scope='row', string=re.compile(r'\s*อินทร์บุรี\s*'))
        
        if not header_cell:
            print("⚠️ ไม่พบช่องหัวข้อของสถานี 'อินทร์บุรี' (th scope=row)")
            return None, None
        
        # 2. ค้นหาแถวแม่ (tr) ของช่องนั้น
        target_row = header_cell.find_parent('tr')

        if not target_row:
             print("⚠️ พบช่องหัวข้อ แต่ไม่พบแถวแม่ (tr) ของสถานี 'อินทร์บุรี'")
             return None, None

        # 3. ค้นหาทุกคอลัมน์ (td) ในแถวนั้น
        cells = target_row.find_all('td')
        
        # ระบุตำแหน่งที่ถูกต้อง: ระดับน้ำ (index=3), ระดับตลิ่ง (index=4)
        if len(cells) >= 5:
            water_level_str = cells[3].text.strip()
            bank_level_str = cells[4].text.strip()
            
            water_level = float(water_level_str)
            bank_level = float(bank_level_str)
            
            print(f"✅ พบข้อมูลอินทร์บุรี: ระดับน้ำ={water_level}, ระดับตลิ่ง={bank_level}")
            return water_level, bank_level
        else:
            print("⚠️ โครงสร้างตารางมีการเปลี่ยนแปลง ไม่พบคอลัมน์ข้อมูลระดับน้ำ")
            return None, None

    except Exception as e:
        print(f"⚠️ ERROR: get_inburi_data (Selenium): {e}"); return None, None
    finally:
        driver.quit()

# --- ดึงข้อมูลเขื่อนเจ้าพระยา ---
def fetch_chao_phraya_dam_discharge(url: str):
    if not SELENIUM_AVAILABLE: return None
    driver = setup_driver()
    try:
        try:
            driver.get(url)
        except TimeoutException:
            print("⚠️ ERROR: หน้าเว็บเขื่อนเจ้าพระยาโหลดไม่เสร็จในเวลาที่กำหนด"); return None

        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, "//script[contains(text(), 'json_data')]")))
        html = driver.page_source
        match = re.search(r'json_data\s*=\s*(\[.*?\]);', html, flags=re.DOTALL)
        if not match: print("⚠️ ไม่พบตัวแปร 'json_data'"); return None
        data = json.loads(match.group(1))
        for entry in data:
            if isinstance(entry, dict) and 'itc_water' in entry and 'C13' in entry['itc_water']:
                storage_val = entry['itc_water']['C13'].get('storage')
                if storage_val:
                    value = float(str(storage_val).replace(',', ''))
                    print(f"✅ พบข้อมูลเขื่อนเจ้าพระยา: {value}"); return value
        print("⚠️ พบ json_data แต่ไม่พบข้อมูล 'C13.storage'"); return None
    except Exception as e:
        print(f"⚠️ ERROR: fetch_chao_phraya_dam_discharge (Selenium): {e}"); return None
    finally:
        driver.quit()

# --- วิเคราะห์และสร้างข้อความ ---
def analyze_and_create_message(inburi_level, dam_discharge, bank_height, hist_2567=None, hist_2565=None, hist_2554=None):
    distance_to_bank = bank_height - inburi_level; ICON, HEADER, summary_text = "", "", ""
    if dam_discharge > 2400 or distance_to_bank < 1.0:
        ICON, HEADER, summary_text = "🟥", "‼️ ประกาศเตือนภัยระดับสูงสุด ‼️", "คำแนะนำ:\n1. เตรียมพร้อมอพยพหากอยู่ในพื้นที่เสี่ยง\n2. ขนย้ายทรัพย์สินขึ้นที่สูงโดยด่วน\n3. งดใช้เส้นทางสัญจรริมแม่น้ำ"
    elif dam_discharge > 1800 or distance_to_bank < 2.0:
        ICON, HEADER, summary_text = "🟨", "‼️ ประกาศเฝ้าระวัง ‼️", "คำแนะนำ:\n1. บ้านเรือนริมตลิ่งนอกคันกั้นน้ำ ให้เริ่มขนของขึ้นที่สูง\n2. ติดตามสถานการณ์อย่างใกล้ชิด"
    else:
        ICON, HEADER, summary_text = "🟩", "สถานะปกติ", "สถานการณ์น้ำยังปกติ ใช้ชีวิตได้ตามปกติครับ"
    now = datetime.now(pytz.timezone('Asia/Bangkok')); TIMESTAMP = now.strftime('%d/%m/%Y %H:%M')
    msg_lines = [ f"{ICON} {HEADER}", "", f"📍 รายงานสถานการณ์น้ำเจ้าพระยา จ.อ.อินทร์บุรี", f"🗓️ วันที่: {TIMESTAMP} น.", "", "🌊 ระดับน้ำ + ระดับตลิ่ง", f"  • อินทร์บุรี: {inburi_level:.2f} ม.รทก.", f"  • ตลิ่ง: {bank_height:.2f} ม.รทก. (ต่ำกว่า {distance_to_bank:.2f} ม.)", "", "💧 ปริมาณน้ำปล่อยเขื่อนเจ้าพระยา", f"  {dam_discharge:,.0f} ลบ.ม./วินาที", "", "🔄 เปรียบเทียบย้อนหลัง", ]
    if hist_2567 is not None: msg_lines.append(f"  • ปี 2567: {hist_2567:,.0f} ลบ.ม./วินาที")
    if hist_2565 is not None: msg_lines.append(f"  • ปี 2565: {hist_2565:,.0f} ลบ.ม./วินาที")
    if hist_2554 is not None: msg_lines.append(f"  • ปี 2554: {hist_2554:,.0f} ลบ.ม./วินาที")
    msg_lines += ["", summary_text]
    return "\n".join(msg_lines)

# --- สร้างข้อความ Error ---
def create_error_message(inburi_status, discharge_status):
    now = datetime.now(pytz.timezone('Asia/Bangkok')); return ( f"⚙️❌ เกิดข้อผิดพลาดในการดึงข้อมูล ❌⚙️\n" f"เวลา: {now.strftime('%d/%m/%Y %H:%M')} น.\n\n" f"• สถานะข้อมูลระดับน้ำอินทร์บุรี: {inburi_status}\n" f"• สถานะข้อมูลเขื่อนเจ้าพระยา: {discharge_status}\n\n" f"กรุณาตรวจสอบ Log บน GitHub Actions" )

# --- ส่งข้อความ LINE ---
def send_line_push(message):
    if not all([LINE_TOKEN, LINE_GROUP_ID]): print("❌ ไม่พบ LINE_TOKEN หรือ LINE_GROUP_ID"); return
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"to": LINE_GROUP_ID, "messages": [{"type": "text", "text": message}]}
    try:
        res = requests.post(LINE_PUSH_API_URL, headers=headers, json=payload, timeout=15); res.raise_for_status()
        print("✅ ส่งข้อความ Push สำเร็จ!")
    except Exception as e: print(f"❌ ERROR: LINE Push: {e}")

# --- Main ---
if __name__ == "__main__":
    print("=== เริ่มการทำงาน ===")
    inburi_level, bank_level = get_inburi_data(SINGBURI_URL)
    dam_discharge = fetch_chao_phraya_dam_discharge(DISCHARGE_URL)
    hist_2567 = get_historical_from_excel(2567); hist_2565 = get_historical_from_excel(2565); hist_2554 = get_historical_from_excel(2554)
    if inburi_level is not None and bank_level is not None and dam_discharge is not None:
        final_message = analyze_and_create_message( inburi_level, dam_discharge, bank_level, hist_2567=hist_2567, hist_2565=hist_2565, hist_2554=hist_2554, )
    else:
        inburi_status = "สำเร็จ" if inburi_level is not None else "ล้มเหลว"
        discharge_status = "สำเร็จ" if dam_discharge is not None else "ล้มเหลว"
        final_message = create_error_message(inburi_status, discharge_status)
    print("\n📤 ข้อความที่จะแจ้งเตือน:"); print(final_message); print("\n🚀 ส่งข้อความไปยัง LINE...")
    send_line_push(final_message); print("✅ เสร็จสิ้นการทำงาน")

# === END OF FILE: main.py ===
