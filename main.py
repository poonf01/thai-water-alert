import os
import re
import json
import time
import requests
import pytz
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

# --- ค่าคงที่ ---
SINGBURI_URL = "https://singburi.thaiwater.net/wl"
DISCHARGE_URL = 'https://tiwrm.hii.or.th/DATA/REPORT/php/chart/chaopraya/small/chaopraya.php'
HISTORICAL_DATA_FILE = 'dam_discharge_history_complete.csv'
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"

# Dictionary to map Thai month names to month numbers
THAI_MONTH_MAP = {
    'มกราคม': 1, 'กุมภาพันธ์': 2, 'มีนาคม': 3, 'เมษายน': 4, 'พฤษภาคม': 5, 'มิถุนายน': 6,
    'กรกฎาคม': 7, 'สิงหาคม': 8, 'กันยายน': 9, 'ตุลาคม': 10, 'พฤศจิกายน': 11, 'ธันวาคม': 12
}

# --- ฟังก์ชันดึงข้อมูลระดับน้ำอินทร์บุรี ---
def get_inburi_data(url: str, timeout: int = 60, retries: int = 3):
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    opts.add_argument("--disable-blink-features=AutomationControlled") # Evade bot detection

    driver = None
    for attempt in range(retries):
        try:
            print(f"Attempt {attempt + 1} to fetch data from {url}")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            driver.get(url)

            # Wait for the table to be present
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.ID, "station-list"))
            )
            
            # Use a more robust selector that doesn't rely on nth-child if possible
            # Looking for the row containing "C.2" for Singburi station
            station_row = driver.find_element(By.XPATH, "//tbody[@id='station-list']//td[contains(text(), 'C.2')]//..")

            # Get level and bank data from the identified row
            level_element = station_row.find_element(By.XPATH, ".//td[2]/span")
            bank_element = station_row.find_element(By.XPATH, ".//td[4]/span")
            
            level = level_element.text.strip()
            bank = bank_element.text.strip()

            if level and bank and level != "N/A" and bank != "N/A":
                print(f"✅ ข้อมูลระดับน้ำ: {level}, ระดับตลิ่ง: {bank}")
                return level, bank
            else:
                print("⚠️ ได้ข้อมูลแต่เป็น N/A, กำลังลองใหม่...")
                time.sleep(5) # Wait before retrying if data is not available yet
                
        except (TimeoutException, StaleElementReferenceException) as e:
            print(f"❌ ERROR: เกิดข้อผิดพลาด (Selenium): {e}. กำลังลองใหม่...")
            if attempt == retries - 1:
                print("❌ Fetching data failed after multiple retries.")
                return None, None
            time.sleep(10) # Wait longer before retrying
        except Exception as e:
            print(f"❌ ERROR: เกิดข้อผิดพลาดทั่วไป: {e}")
            return None, None
        finally:
            if driver:
                driver.quit()
    return None, None

# --- ฟังก์ชันดึงข้อมูลการปล่อยน้ำเขื่อนเจ้าพระยา ---
def fetch_chao_phraya_dam_discharge(url: str):
    try:
        headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
        res = requests.get(url, headers=headers, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        # Find the script tag containing the data
        scripts = soup.find_all('script')
        data_script = None
        for script in scripts:
            if 'chaopraya_dam_storage' in script.text:
                data_script = script.text
                break
        
        if not data_script:
            print("❌ ไม่พบ Script ที่มีข้อมูลน้ำ")
            return None

        # Extract the latest discharge value (it's usually the last one in the series)
        matches = re.findall(r"parseFloat\('([0-9.]+)'\)", data_script)
        if matches:
            discharge_value = matches[-1] # Get the last value in the array
            print(f"✅ ปริมาณน้ำไหลผ่านเขื่อนเจ้าพระยา: {discharge_value}")
            return discharge_value
        else:
            print("❌ ไม่พบข้อมูลการปล่อยน้ำใน Script")
            return None

    except requests.exceptions.RequestException as e:
        print(f"❌ ERROR: ไม่สามารถเชื่อมต่อได้: {e}")
        return None
    except Exception as e:
        print(f"❌ ERROR: เกิดข้อผิดพลาดในการดึงข้อมูลเขื่อน: {e}")
        return None


# --- ฟังก์ชันจัดการข้อมูลย้อนหลัง ---
def load_historical_data(file_path):
    try:
        df = pd.read_csv(file_path)
        df['เดือน'] = df['เดือน'].str.strip().map(THAI_MONTH_MAP)
        # Convert Buddhist year to Christian year for datetime conversion
        df['ปี'] = df['ปี'] - 543
        df['date'] = pd.to_datetime(df[['ปี', 'เดือน', 'วันที่']].rename(columns={'ปี': 'year', 'เดือน': 'month', 'วันที่': 'day'}))
        return df
    except FileNotFoundError:
        print(f"❌ ERROR: ไม่พบไฟล์ {file_path}")
        return None
    except Exception as e:
        print(f"❌ ERROR: เกิดข้อผิดพลาดในการโหลดข้อมูลย้อนหลัง: {e}")
        return None

def find_historical_discharge(df, target_date):
    if df is None:
        return "ไม่มีข้อมูล"
    try:
        # Compare month and day
        match = df[df['date'].dt.strftime('%m-%d') == target_date.strftime('%m-%d')]
        if not match.empty:
            # If multiple entries for the same day, take the last one.
            return match['ปริมาณน้ำ (ลบ.ม./วินาที)'].iloc[-1]
        else:
            return "ไม่มีข้อมูล"
    except Exception:
        return "หาข้อมูลไม่ได้"

# --- ฟังก์ชันสร้างและส่งข้อความ ---
def analyze_and_create_message(current_level, current_discharge, bank_level, hist_2024, hist_2011):
    today_th = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%d %B %Y %H:%M')

    try:
        level_float = float(current_level)
        bank_float = float(bank_level)
        remaining = bank_float - level_float
        
        if level_float >= bank_float:
            status = "🚨 ระดับน้ำถึงตลิ่งแล้ว! 🚨"
        elif remaining <= 1.0:
            status = "❗❗ แจ้งเตือนระดับน้ำใกล้ถึงตลิ่ง ❗❗"
        elif remaining <= 2.0:
            status = "⚠️ แจ้งเตือนระดับน้ำ"
        else:
            status = "💧 สถานการณ์น้ำปกติ"
    except (ValueError, TypeError):
        level_float = 0
        bank_float = 0
        remaining = 0
        status = "❌ ไม่สามารถประมวลผลข้อมูลระดับน้ำได้"

    message = (
        f"📢 สรุปสถานการณ์น้ำ {today_th} (GMT+7)\n"
        f"=========================\n"
        f"🌊 **สถานีวัดน้ำ C.2 อ.เมืองสิงห์บุรี**\n"
        f"   - ระดับน้ำ: **{current_level} ม.** (รทก.)\n"
        f"   - ระดับตลิ่ง: **{bank_level} ม.** (รทก.)\n"
        f"   - ต่ำกว่าตลิ่ง: **{remaining:.2f} ม.**\n"
        f"   - สถานะ: {status}\n"
        f"=========================\n"
        f"댐 **เขื่อนเจ้าพระยา (C.13)**\n"
        f"   - ปริมาณน้ำไหลผ่าน (ล่าสุด):\n"
        f"     **{current_discharge} ลบ.ม./วินาที**\n\n"
        f"   - **เปรียบเทียบข้อมูลย้อนหลัง (ณ วันเดียวกัน):**\n"
        f"     - ปี 2567 (2024): **{hist_2024}** ลบ.ม./วินาที\n"
        f"     - ปี 2554 (2011): **{hist_2011}** ลบ.ม./วินาที\n"
        f"=========================\n"
        f"#แจ้งเตือนน้ำสิงห์บุรี #เขื่อนเจ้าพระยา"
    )
    return message.strip()

def send_line_broadcast(message):
    if not LINE_TOKEN:
        print("❌ ERROR: ไม่ได้ตั้งค่า LINE_CHANNEL_ACCESS_TOKEN")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    # Use data=json.dumps(payload) for LINE API
    payload = {
        "messages": [{
            "type": "text",
            "text": message
        }]
    }
    try:
        res = requests.post(LINE_API_URL, headers=headers, data=json.dumps(payload), timeout=10)
        res.raise_for_status()
        print("✅ ส่งข้อความ Broadcast สำเร็จ!")
    except Exception as e:
        print(f"❌ ERROR: LINE Broadcast: {e}")

# --- Main ---
if __name__ == "__main__":
    print("=== เริ่มการทำงานระบบแจ้งเตือนน้ำอินทร์บุรี ===")
    
    inburi_level, bank_level = get_inburi_data(SINGBURI_URL)
    dam_discharge = fetch_chao_phraya_dam_discharge(DISCHARGE_URL)
    
    historical_df = load_historical_data(HISTORICAL_DATA_FILE)
    
    today = datetime.now(pytz.timezone('Asia/Bangkok'))
    
    # Create target dates for comparison by replacing the year
    target_date_2024 = today.replace(year=2024)
    target_date_2011 = today.replace(year=2011)
    
    hist_2567 = find_historical_discharge(historical_df, target_date_2024)
    hist_2554 = find_historical_discharge(historical_df, target_date_2011)

    if inburi_level is not None and bank_level is not None and dam_discharge is not None:
        final_message = analyze_and_create_message(inburi_level, dam_discharge, bank_level, hist_2567, hist_2554)
        print("\n--- ข้อความที่จะส่ง ---")
        print(final_message)
        print("--------------------\n")
        send_line_broadcast(final_message)
    else:
        inburi_status = "สำเร็จ" if inburi_level is not None else "ล้มเหลว"
        dam_status = "สำเร็จ" if dam_discharge is not None else "ล้มเหลว"
        error_message = (
            f"❌ เกิดข้อผิดพลาดในการดึงข้อมูลบางส่วน\n"
            f"- สถานะข้อมูลระดับน้ำสิงห์บุรี: {inburi_status}\n"
            f"- สถานะข้อมูลเขื่อนเจ้าพระยา: {dam_status}\n"
            f"ไม่สามารถส่งข้อความแจ้งเตือนได้"
        )
        print(error_message)
        # Optionally send an error notification
        # send_line_broadcast(error_message)
