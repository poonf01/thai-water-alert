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
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- ค่าคงที่ (แก้ไข Path ให้ยืดหยุ่นขึ้น) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SINGBURI_URL = "https://singburi.thaiwater.net/wl"
DISCHARGE_URL = 'https://tiwrm.hii.or.th/DATA/REPORT/php/chart/chaopraya/small/chaopraya.php'
HISTORICAL_DATA_FILE = os.path.join(BASE_DIR, 'data', 'dam_discharge_history_complete.csv')
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"

# แผนที่ชื่อเดือนไทย → เดือนตัวเลข
THAI_MONTH_MAP = {
    'มกราคม': 1, 'กุมภาพันธ์': 2, 'มีนาคม': 3, 'เมษายน': 4,
    'พฤษภาคม': 5, 'มิถุนายน': 6, 'กรกฎาคม': 7, 'สิงหาคม': 8,
    'กันยายน': 9, 'ตุลาคม': 10, 'พฤศจิกายน': 11, 'ธันวาคม': 12
}

# --- ฟังก์ชันดึงข้อมูลระดับน้ำอินทร์บุรี ---
def get_inburi_data(url: str, timeout: int = 90, retries: int = 3):
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0")
    opts.add_argument("--disable-blink-features=AutomationControlled")

    driver = None
    for attempt in range(retries):
        try:
            driver = webdriver.Chrome(options=opts)
            driver.get(url)
            wait = WebDriverWait(driver, timeout)
            # ปรับ XPath ให้จับ C.2 (อินทร์บุรี) ได้ตรง
            station_row = wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, "//tbody[@id='station-list']//th[contains(text(), 'อินทร์บุรี')]/parent::tr")
                )
            )
            level = station_row.find_element(By.XPATH, ".//td[2]/span").text.strip()
            bank  = station_row.find_element(By.XPATH, ".//td[3]/span").text.strip()
            if level and bank and level != "N/A" and bank != "N/A":
                return level, bank
        except Exception as e:
            print(f"[get_inburi_data] Attempt {attempt+1} failed: {e}")
        finally:
            if driver:
                driver.quit()
        time.sleep(5)
    print("❌ ดึงข้อมูลระดับน้ำอินทร์บุรีล้มเหลวหลังลองหลายครั้ง")
    return None, None

# --- ฟังก์ชันดึงข้อมูลการปล่อยน้ำเขื่อนเจ้าพระยา ---
def fetch_chao_phraya_dam_discharge(url: str):
    try:
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        # หาเลขทุกรูปแบบ และเลือกตัวสุดท้าย
        nums = re.findall(r"([-+]?\d*\.\d+|\d+)", res.text)
        if nums:
            return nums[-1]
    except Exception as e:
        print(f"[fetch_chao_phraya_dam_discharge] Error: {e}")
    return None

# --- ฟังก์ชันโหลดและดีบักข้อมูลย้อนหลัง ---
def load_historical_data(path):
    try:
        print(f"🔍 Loading historical data from: {path}")
        df = pd.read_csv(path)
        print("DEBUG: columns =", df.columns.tolist())
        print("DEBUG: head =\n", df.head(5))
        df['เดือน'] = df['เดือน'].str.strip().map(THAI_MONTH_MAP)
        df['ปี']   = df['ปี'] - 543
        df['date'] = pd.to_datetime(
            df[['ปี','เดือน','วันที่']].rename(
                columns={'ปี':'year','เดือน':'month','วันที่':'day'}
            )
        )
        print("DEBUG: parsed dates =\n", df['date'].head(5))
        return df
    except Exception as e:
        print(f"❌ [load_historical_data] Error: {e}")
        return None

# --- ฟังก์ชันค้นหาปริมาณน้ำย้อนหลังตามปีตรง ---
def find_historical_discharge(df, target_date):
    if df is None:
        return "ไม่มีข้อมูล"
    # ดีบักการค้นหา
    print(f"🔎 Looking for exact date: {target_date.strftime('%Y-%m-%d')}")
    exact = df[df['date'] == target_date]
    if not exact.empty:
        print("DEBUG: Found exact match:\n", exact[['date','ปริมาณน้ำ (ลบ.ม./วินาที)']])
        return str(exact['ปริมาณน้ำ (ลบ.ม./วินาที)'].iloc[0])
    # fallback: match by month-day
    mmdd = target_date.strftime('%m-%d')
    subset = df[df['date'].dt.strftime('%m-%d') == mmdd]
    print(f"DEBUG: Fallback month-day filter {mmdd} → {len(subset)} rows")
    if not subset.empty:
        return str(subset['ปริมาณน้ำ (ลบ.ม./วินาที)'].iloc[0])
    return "ไม่มีข้อมูล"

# --- สร้างข้อความสรุป ---
def analyze_and_create_message(current_level, discharge, bank_level, hist_2024, hist_2011):
    now = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%d %B %Y %H:%M')
    status = "💧 สถานการณ์น้ำปกติ"
    try:
        lf = float(current_level)
        bf = float(bank_level)
        diff = bf - lf
        if lf >= bf:        status = "🚨 ถึงตลิ่งแล้ว! 🚨"
        elif diff <= 1.0:    status = "❗ ใกล้ตลิ่ง ❗"
        elif diff <= 2.0:    status = "⚠️ แจ้งเตือน"
    except:
        status = "❌ ข้อมูลระดับน้ำผิดรูป"
    msg = (
        f"📢 น้ำ ณ {now} (GMT+7)\n"
        f"- อินทร์บุรี: น้ำ {current_level} ม. / ตลิ่ง {bank_level} ม.\n"
        f"- สถานะ: {status}\n"
        f"- เขื่อนเจ้าพระยา: {discharge} ลบ.ม./วินาที\n"
        f"- ย้อนหลัง: 2567={hist_2024}, 2554={hist_2011}"
    )
    return msg

# --- ส่ง LINE ---
def send_line_broadcast(message):
    if not LINE_TOKEN:
        print("❌ ไม่มี LINE_CHANNEL_ACCESS_TOKEN")
        return
    headers = {"Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"messages": [{"type":"text","text":message}]}
    try:
        r = requests.post(LINE_API_URL, headers=headers, json=payload, timeout=10)
        r.raise_for_status()
        print("✅ Sent LINE broadcast")
    except Exception as e:
        print(f"❌ [send_line] Error: {e}")

# --- Main ---
if __name__ == "__main__":
    print("=== เริ่มระบบแจ้งเตือนน้ำอินทร์บุรี ===")
    lvl, bank = get_inburi_data(SINGBURI_URL)
    dis  = fetch_chao_phraya_dam_discharge(DISCHARGE_URL)
    df_hist = load_historical_data(HISTORICAL_DATA_FILE)

    today = datetime.now(pytz.timezone('Asia/Bangkok'))
    h_2024 = find_historical_discharge(df_hist, today.replace(year=2024))
    h_2011 = find_historical_discharge(df_hist, today.replace(year=2011))

    if lvl and bank and dis:
        message = analyze_and_create_message(lvl, dis, bank, h_2024, h_2011)
        print(message)
        send_line_broadcast(message)
    else:
        print("❌ ดึงข้อมูลไม่ครบ ไม่สามารถแจ้งเตือนได้")
