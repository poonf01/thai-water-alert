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
# พยายามนำเข้า Selenium และโมดูลที่เกี่ยวข้อง เผื่อในสภาพแวดล้อมไม่มีติดตั้ง
try:
    from selenium import webdriver  # type: ignore
    from selenium.webdriver.chrome.options import Options  # type: ignore
    from selenium.webdriver.chrome.service import Service  # type: ignore
    from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
    from selenium.webdriver.common.by import By  # type: ignore
    from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
    from selenium.webdriver.support import expected_conditions as EC  # type: ignore
    from selenium.common.exceptions import StaleElementReferenceException  # type: ignore
except Exception:
    # หากไม่สามารถนำเข้าได้ ให้ตั้งค่าเป็น None เพื่อให้สคริปต์ยังทำงานได้เมื่อไม่ใช้ Selenium
    webdriver = None  # type: ignore
    Options = None  # type: ignore
    Service = None  # type: ignore
    ChromeDriverManager = None  # type: ignore
    By = None  # type: ignore
    WebDriverWait = None  # type: ignore
    EC = None  # type: ignore
    StaleElementReferenceException = Exception

# --- ค่าคงที่ ---
SINGBURI_URL = "https://singburi.thaiwater.net/wl"
DISCHARGE_URL = 'https://tiwrm.hii.or.th/DATA/REPORT/php/chart/chaopraya/small/chaopraya.php'
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_GROUP_ID = os.environ.get('LINE_GROUP_ID') # Get Group ID from environment variable
LINE_PUSH_API_URL = "https://api.line.me/v2/bot/message/push"

# -- อ่านข้อมูลย้อนหลังจาก Excel --
THAI_MONTHS = {
    'มกราคม':1, 'กุมภาพันธ์':2, 'มีนาคม':3, 'เมษายน':4,
    'พฤษภาคม':5, 'มิถุนายน':6, 'กรกฎาคม':7, 'สิงหาคม':8,
    'กันยายน':9, 'ตุลาคม':10, 'พฤศจิกายน':11, 'ธันวาคม':12
}
def get_historical_from_excel(year_be: int) -> int | None:
    """
    อ่านไฟล์ระดับน้ำปี {year_be} จากทั้งโฟลเดอร์ data/ และโฟลเดอร์ปัจจุบัน
    คืนค่า discharge (ลบ.ม./วิ) ของวัน–เดือนปัจจุบัน (ตามเขตเวลาเอเชีย/กรุงเทพ)

    รองรับหลายรูปแบบคอลัมน์ เช่น:
      - มีคอลัมน์ 'เดือน' (ชื่อเดือนภาษาไทย) และ 'วันที่' (ตัวเลข) และคอลัมน์ปริมาณน้ำเป็น 'ปริมาณน้ำ (ลบ.ม./วินาที)' หรือ 'ปริมาณน้ำ (ลบ.ม./วิ)'
      - มีคอลัมน์ 'วันที่' เป็นชนิด datetime และคอลัมน์ค่าปริมาณน้ำอื่น ๆ (เช่น 'ค่า (ปี 2022)')
    """
    import pandas as pd
    # ค้นหาไฟล์ตามชื่อ
    possible_paths = [f"data/ระดับน้ำปี{year_be}.xlsx", f"ระดับน้ำปี{year_be}.xlsx", f"/mnt/data/ระดับน้ำปี{year_be}.xlsx"]
    file_path = None
    for p in possible_paths:
        if os.path.exists(p):
            file_path = p
            break
    if file_path is None:
        print(f"⚠️ ไม่พบไฟล์ข้อมูลย้อนหลังปี {year_be} ใน {possible_paths}")
        return None
    try:
        df = pd.read_excel(file_path)
        # หาคอลัมน์ค่าปริมาณน้ำที่อาจจะมีหลายชื่อ
        discharge_col = None
        for col in df.columns:
            name = str(col)
            if 'ลบ.ม.' in name or 'discharge' in name or 'ค่า' in name:
                discharge_col = col
                break
        if discharge_col is None:
            print(f"⚠️ ไฟล์ {file_path} ไม่มีคอลัมน์ปริมาณน้ำที่รู้จัก")
            return None
        df = df.rename(columns={discharge_col: 'discharge'})
        # ตรวจว่าเรามีคอลัมน์ 'เดือน' และ 'วันที่' แยกหรือไม่
        if 'เดือน' in df.columns and 'วันที่' in df.columns:
            # กรณีนี้ 'วันที่' เป็นตัวเลข (ไม่ใช่ datetime) และ 'เดือน' เป็นชื่อภาษาไทย
            df['month_num'] = df['เดือน'].map(THAI_MONTHS)
            df['day_num'] = df['วันที่']
        elif 'วันที่' in df.columns:
            # แปลง 'วันที่' ให้เป็น datetime หากไม่ใช่
            if not pd.api.types.is_datetime64_any_dtype(df['วันที่']):
                df['date'] = pd.to_datetime(df['วันที่'], errors='coerce')
            else:
                df['date'] = df['วันที่']
            df['month_num'] = df['date'].dt.month
            df['day_num'] = df['date'].dt.day
        else:
            print(f"⚠️ ไฟล์ {file_path} ไม่มีคอลัมน์ 'วันที่' ที่คาดหวัง")
            return None
        # วันที่วันนี้
        now = datetime.now(pytz.timezone('Asia/Bangkok'))
        today_d = now.day
        today_m = now.month
        match = df[(df['day_num'] == today_d) & (df['month_num'] == today_m)]
        if not match.empty:
            val = match.iloc[0]['discharge']
            # แปลงเป็นตัวเลข int หากจำเป็น
            try:
                # หากมี comma
                val_int = int(val)
            except Exception:
                try:
                    val_int = int(str(val).replace(',', ''))
                except Exception:
                    val_int = None
            if val_int is not None:
                print(f"✅ พบข้อมูลย้อนหลังสำหรับปี {year_be}: {val_int} ลบ.ม./วินาที (ไฟล์: {file_path})")
                return val_int
        print(f"⚠️ ไม่พบข้อมูลสำหรับวันที่ {today_d}/{today_m} ในไฟล์ปี {year_be} (ไฟล์: {file_path})")
        return None
    except Exception as e:
        print(f"❌ ERROR: ไม่สามารถโหลดข้อมูลย้อนหลังจาก Excel ได้ ({file_path}): {e}")
        return None

# --- ดึงระดับน้ำอินทร์บุรี ---
def get_inburi_data(url: str, timeout: int = 45, retries: int = 3):
    """
    ดึงข้อมูลระดับน้ำจากหน้าเว็บศูนย์ข้อมูลน้ำของจังหวัดสิงห์บุรี

    ฟังก์ชันนี้พยายามดึงหน้า HTML ด้วย requests แทนการใช้ Selenium เพื่อลดข้อผิดพลาดจาก
    headless browser และทำให้ใช้งานง่ายขึ้นบน GitHub Actions หรือสภาพแวดล้อมที่ไม่มี X-Server.

    ขั้นตอนการทำงาน:
    1. ส่ง HTTP GET ไปยัง URL ที่ระบุ พร้อมตั้ง header เพื่อป้องกันการบล็อกจากเว็บไซต์
    2. แปลงผลลัพธ์เป็น BeautifulSoup แล้วค้นหาแถว (tr) ที่มีคำว่า "อินทร์บุรี"
    3. เมื่อพบแถวดังกล่าว จะดึงตัวเลขทั้งหมดในแถว ด้วย regex แล้วเลือกค่าแรกเป็น
       ระดับน้ำ และค่าที่สองเป็นระดับตลิ่ง หากไม่พบค่าที่สองจะกำหนดไว้ล่วงหน้า

    หากเกิดข้อผิดพลาดระหว่างการดึงข้อมูล จะลองใหม่ตามจำนวน retries ที่กำหนด

    Args:
        url (str): URL ของหน้าเว็บที่ต้องการดึงข้อมูล
        timeout (int): ระยะเวลารอแต่ละครั้ง (วินาที)
        retries (int): จำนวนครั้งที่พยายามใหม่ เมื่อเกิดข้อผิดพลาด

    Returns:
        tuple[float | None, float | None]: (ระดับน้ำ, ระดับตลิ่ง) หรือ (None, None) หากไม่สามารถดึงได้
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
                      'AppleWebKit/537.36 (KHTML, like Gecko) ' +
                      'Chrome/91.0.4472.124 Safari/537.36',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
    for attempt in range(retries):
        try:
            # เพิ่ม cache busting เพื่อป้องกันการเก็บหน้าไว้ใน cache ของเซิร์ฟเวอร์
            cache_buster_url = f"{url}&cb={random.randint(10000, 99999)}" if '?' in url else f"{url}?cb={random.randint(10000, 99999)}"
            resp = requests.get(cache_buster_url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # ค้นหาแถวที่มีคำว่า "อินทร์บุรี" ในข้อความทั้งหมด
            row = None
            for tr in soup.find_all('tr'):
                try:
                    if 'อินทร์บุรี' in tr.get_text():
                        row = tr
                        break
                except Exception:
                    continue
            if row is None:
                print("⚠️ ไม่พบข้อมูลสถานี 'อินทร์บุรี' ในตาราง")
                return None, None

            # แปลงข้อความในแถวเป็นตัวเลขทั้งหมด เช่น 13.28, 15.1, 0.79
            row_text = row.get_text(separator=' ', strip=True)
            # หาเลขทศนิยม/จำนวนเต็ม โดยรองรับเครื่องหมาย comma
            num_strs = re.findall(r'[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?', row_text)
            # แปลงเป็น float โดยลบ comma
            values = []
            for ns in num_strs:
                try:
                    values.append(float(ns.replace(',', '')))
                except Exception:
                    continue
            if not values:
                print("⚠️ ไม่พบข้อมูลตัวเลขสำหรับสถานี 'อินทร์บุรี'")
                return None, None
            # เดาค่า: ตัวแรกเป็นระดับน้ำ ตัวถัดไปที่มากกว่าหรือเท่ากันเป็นระดับตลิ่ง
            water_level = values[0]
            bank_level = None
            for v in values[1:]:
                if v >= water_level:
                    bank_level = v
                    break
            if bank_level is None:
                # หากไม่มีค่าใหญ่กว่า แสดงว่ามีเพียงค่าระดับน้ำ ให้ใช้ค่าตลิ่งมาตรฐาน 13.0 ม.รทก.
                bank_level = 13.0

            print(f"✅ พบข้อมูลอินทร์บุรี: ระดับน้ำ={water_level}, ระดับตลิ่ง={bank_level}")
            return water_level, bank_level
        except Exception as e:
            print(f"⚠️ ERROR: get_inburi_data (ครั้งที่ {attempt + 1}/{retries}): {e}")
            # รอแล้วลองใหม่
            time.sleep(3)
            continue
    return None, None

# --- ดึงข้อมูลเขื่อนเจ้าพระยา (เพิ่ม Cache Busting) ---
def fetch_chao_phraya_dam_discharge(url: str, timeout: int = 30, retries: int = 3):
    """
    ดึงข้อมูลปริมาณน้ำปล่อยเขื่อนเจ้าพระยา

    เนื่องจากหน้าเว็บอาจมีการปรับโครงสร้าง JavaScript อยู่เสมอ ทำให้การดึงข้อมูลด้วย
    regex เดิมอาจไม่พบข้อมูล เราจึงเพิ่มการตรวจสอบหลายรูปแบบ เช่น ตัวแปร json_data ที่มี
    การขึ้นต้นด้วยคำว่า json_data หรือค้นหาข้อมูล "C13" และคีย์ "storage" ในหน้าทั้งหมด
    หากพบก็จะพยายามแปลงเป็นตัวเลข float โดยลบ comma.

    Args:
        url (str): URL ที่ชี้ไปยังหน้า PHP ที่มีข้อมูล
        timeout (int): ระยะเวลารอคำตอบ (วินาที)
        retries (int): จำนวนครั้งที่จะลองใหม่เมื่อเจอข้อผิดพลาด

    Returns:
        float | None: ค่าปริมาณน้ำ (ลบ.ม./วินาที) หรือ None หากไม่พบข้อมูล
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
                      'AppleWebKit/537.36 (KHTML, like Gecko) ' +
                      'Chrome/91.0.4472.124 Safari/537.36',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
    for attempt in range(retries):
        try:
            cache_buster_url = f"{url}?cb={random.randint(10000, 99999)}"
            response = requests.get(cache_buster_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            response.encoding = 'utf-8'
            text = response.text

            # รูปแบบเดิม: var json_data = [ ... ]; อาจมีการขึ้นต้นด้วยคำว่า const/let หรือมีช่องว่าง
            match = re.search(r'json_data\s*=\s*(\[.*?\]);', text, flags=re.DOTALL)
            data = None
            if match:
                json_string = match.group(1)
                try:
                    data = json.loads(json_string)
                except Exception as e:
                    # บางครั้ง JSON มี comment หรือ comma เกิน ต้องทำความสะอาดเบื้องต้น
                    cleaned = re.sub(r'/\*.*?\*/', '', json_string, flags=re.DOTALL)  # ลบคอมเมนต์
                    cleaned = re.sub(r',\s*\]', ']', cleaned)  # ลบ comma ท้ายอาร์เรย์
                    data = json.loads(cleaned)
            # หากพาร์ส json_data สำเร็จ
            if isinstance(data, list) and data:
                # วนหา C13.Storage ภายในข้อมูล
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    # กรณีมี itc_water แล้วมี C13
                    if 'itc_water' in entry and isinstance(entry['itc_water'], dict):
                        c13 = entry['itc_water'].get('C13')
                        if isinstance(c13, dict) and 'storage' in c13:
                            raw_val = c13['storage']
                            try:
                                value = float(raw_val) if isinstance(raw_val, (int, float)) else float(str(raw_val).replace(',', ''))
                                print(f"✅ พบข้อมูลเขื่อนเจ้าพระยา: {value}")
                                return value
                            except Exception:
                                pass
                    # กรณีมี C13 อยู่ใน entry
                    if 'C13' in entry and isinstance(entry['C13'], dict) and 'storage' in entry['C13']:
                        raw_val = entry['C13']['storage']
                        try:
                            value = float(raw_val) if isinstance(raw_val, (int, float)) else float(str(raw_val).replace(',', ''))
                            print(f"✅ พบข้อมูลเขื่อนเจ้าพระยา: {value}")
                            return value
                        except Exception:
                            pass
            # หากไม่พบ json_data ให้ค้นหารูปแบบตรง ๆ ใน HTML (เช่น "C13": {"storage": "2,400"})
            pattern = re.search(r'"C13"\s*:\s*\{[^\}]*?"storage"\s*:\s*"?([0-9,\.]+)', text)
            if pattern:
                num_str = pattern.group(1)
                try:
                    value = float(num_str.replace(',', ''))
                    print(f"✅ พบข้อมูลเขื่อนเจ้าพระยา: {value}")
                    return value
                except Exception:
                    pass

            print("⚠️ ไม่พบข้อมูล JSON หรือ storage สำหรับ 'C13' ในหน้าเว็บนี้")
            return None
        except Exception as e:
            print(f"⚠️ ERROR: fetch_chao_phraya_dam_discharge (ครั้งที่ {attempt + 1}/{retries}): {e}")
            time.sleep(3)
            continue
    return None

# --- วิเคราะห์และสร้างข้อความ ---
def analyze_and_create_message(inburi_level, dam_discharge, bank_height, hist_2567=None, hist_2565=None, hist_2554=None):
    distance_to_bank = bank_height - inburi_level
    
    ICON = ""
    HEADER = ""
    summary_text = ""

    if dam_discharge > 2400 or distance_to_bank < 1.0:
        ICON = "🟥"
        HEADER = "‼️ ประกาศเตือนภัยระดับสูงสุด ‼️"
        summary_text = "คำแนะนำ:\n1. เตรียมพร้อมอพยพหากอยู่ในพื้นที่เสี่ยง\n2. ขนย้ายทรัพย์สินขึ้นที่สูงโดยด่วน\n3. งดใช้เส้นทางสัญจรริมแม่น้ำ"
    elif dam_discharge > 1800 or distance_to_bank < 2.0:
        ICON = "🟨"
        HEADER = "‼️ ประกาศเฝ้าระวัง ‼️"
        summary_text = "คำแนะนำ:\n1. บ้านเรือนริมตลิ่งนอกคันกั้นน้ำ ให้เริ่มขนของขึ้นที่สูง\n2. ติดตามสถานการณ์อย่างใกล้ชิด"
    else:
        ICON = "🟩"
        HEADER = "สถานะปกติ"
        summary_text = "สถานการณ์น้ำยังปกติ ใช้ชีวิตได้ตามปกติครับ"

    now = datetime.now(pytz.timezone('Asia/Bangkok'))
    TIMESTAMP = now.strftime('%d/%m/%Y %H:%M')

    msg_lines = [
        f"{ICON} {HEADER}",
        "",
        f"📍 รายงานสถานการณ์น้ำเจ้าพระยา จ.อ.อินทร์บุรี",
        f"🗓️ วันที่: {TIMESTAMP} น.",
        "",
        "🌊 ระดับน้ำ + ระดับตลิ่ง",
        f"  • อินทร์บุรี: {inburi_level:.2f} ม.รทก.",
        f"  • ตลิ่ง: {bank_height:.2f} ม.รทก. (ต่ำกว่า {distance_to_bank:.2f} ม.)",
        "",
        "💧 ปริมาณน้ำปล่อยเขื่อนเจ้าพระยา",
        f"  {dam_discharge:,} ลบ.ม./วินาที",
        "",
        "🔄 เปรียบเทียบย้อนหลัง",
    ]
    if hist_2567 is not None:
        msg_lines.append(f"  • ปี 2567: {hist_2567:,} ลบ.ม./วินาที")
    if hist_2565 is not None:
        msg_lines.append(f"  • ปี 2565: {hist_2565:,} ลบ.ม./วินาที")
    if hist_2554 is not None:
        msg_lines.append(f"  • ปี 2554: {hist_2554:,} ลบ.ม./วินาที")
    msg_lines += [
        "",
        summary_text
    ]
    return "\n".join(msg_lines)

# --- สร้างข้อความ Error ---
def create_error_message(inburi_status, discharge_status):
    now = datetime.now(pytz.timezone('Asia/Bangkok'))
    return (
        f"⚙️❌ เกิดข้อผิดพลาดในการดึงข้อมูล ❌⚙️\n"
        f"เวลา: {now.strftime('%d/%m/%Y %H:%M')} น.\n\n"
        f"• สถานะข้อมูลระดับน้ำอินทร์บุรี: {inburi_status}\n"
        f"• สถานะข้อมูลเขื่อนเจ้าพระยา: {discharge_status}\n\n"
        f"กรุณาตรวจสอบ Log บน GitHub Actions เพื่อดูรายละเอียดข้อผิดพลาดครับ"
    )

# --- ส่งข้อความ LINE (ฉบับปรับปรุง) ---
def send_line_push(message):
    if not LINE_TOKEN:
        print("❌ ไม่พบ LINE_CHANNEL_ACCESS_TOKEN!")
        return
    if not LINE_GROUP_ID:
        print("❌ ไม่พบ LINE_GROUP_ID! กรุณาตั้งค่าใน GitHub Secrets")
        return

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    # Payload for Push Message
    payload = {
        "to": LINE_GROUP_ID,
        "messages": [{"type": "text", "text": message}]
    }
    
    retries = 3 # จำนวนครั้งที่จะลองใหม่
    delay = 5   # เริ่มต้นรอ 5 วินาที

    for i in range(retries):
        try:
            # Use the PUSH API URL
            res = requests.post(LINE_PUSH_API_URL, headers=headers, json=payload, timeout=15)
            res.raise_for_status() 
            
            print("✅ ส่งข้อความ Push สำเร็จ!")
            return
            
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 429:
                print(f"⚠️ API แจ้งว่าส่งถี่เกินไป (429), กำลังลองใหม่ในอีก {delay} วินาที... (ครั้งที่ {i + 1}/{retries})")
                time.sleep(delay)
                delay *= 2
            else:
                print(f"❌ ERROR: LINE Push (HTTP Error): {err}")
                print(f"    Response: {err.response.text}") # Print error response for more details
                break
        except Exception as e:
            print(f"❌ ERROR: LINE Push (General Error): {e}")
            break

    print("❌ ไม่สามารถส่งข้อความได้หลังจากการพยายามหลายครั้ง")


# --- Main ---
if __name__ == "__main__":
    print("=== เริ่มการทำงานระบบแจ้งเตือนน้ำอินทร์บุรี ===")
    
    inburi_cache_buster_url = f"{SINGBURI_URL}?cb={random.randint(10000, 99999)}"
    
    inburi_level, bank_level = get_inburi_data(inburi_cache_buster_url)
    dam_discharge = fetch_chao_phraya_dam_discharge(DISCHARGE_URL)
    
    # ดึงข้อมูลย้อนหลังจาก Excel (ตามวันวันนี้)
    hist_2567 = get_historical_from_excel(2567)
    hist_2565 = get_historical_from_excel(2565)
    hist_2554 = get_historical_from_excel(2554)

    if inburi_level is not None and bank_level is not None and dam_discharge is not None:
        final_message = analyze_and_create_message(
            inburi_level,
            dam_discharge,
            bank_level,
            hist_2567=hist_2567,
            hist_2565=hist_2565,
            hist_2554=hist_2554,
        )
    else:
        inburi_status = "สำเร็จ" if inburi_level is not None else "ล้มเหลว"
        discharge_status = "สำเร็จ" if dam_discharge is not None else "ล้มเหลว"
        final_message = create_error_message(inburi_status, discharge_status)

    print("\n📤 ข้อความที่จะแจ้งเตือน:")
    print(final_message)
    print("\n🚀 ส่งข้อความไปยัง LINE...")
    send_line_push(final_message)
    print("✅ เสร็จสิ้นการทำงาน")
