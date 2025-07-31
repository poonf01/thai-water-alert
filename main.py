import os
import re
import json
import time
import requests
import pytz
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

# --- ค่าคงที่ (แก้ไข Path กลับมาให้ถูกต้อง) ---
SINGBURI_URL = "https://singburi.thaiwater.net/wl"
DISCHARGE_URL = 'https://tiwrm.hii.or.th/DATA/REPORT/php/chart/chaopraya/small/chaopraya.php'
HISTORICAL_DATA_FILE = 'data/dam_discharge_history_complete.csv'
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"

# Dictionary to map Thai month names to month numbers
THAI_MONTH_MAP = {
    'มกราคม': 1, 'กุมภาพันธ์': 2, 'มีนาคม': 3, 'เมษายน': 4, 'พฤษภาคม': 5, 'มิถุนายน': 6,
    'กรกฎาคม': 7, 'สิงหาคม': 8, 'กันยายน': 9, 'ตุลาคม': 10, 'พฤศจิกายน': 11, 'ธันวาคม': 12
}

# --- ฟังก์ชันดึงข้อมูลระดับน้ำอินทร์บุรี ---
def get_inburi_data(url: str, timeout: int = 20):
    """
    ดึงระดับน้ำและระดับตลิ่งจากหน้าเว็บอินทร์บุรี
    คืนค่า (level, bank) หรือ (None, None) กรณีไม่สำเร็จ
    """
    try:
        print(f"Fetching data from {url}")
        res = requests.get(url, timeout=timeout)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        # ค้นหาแถวที่มีสถานี "อินทร์บุรี"
        row = None
        # ถ้า bs4 >=4.7 ใช้ :has() กับ :contains()
        try:
            row = soup.select_one("tbody#station-list tr:has(th:contains('อินทร์บุรี'))")
        except Exception:
            # fallback สำหรับ bs4 รุ่นก่อน
            for r in soup.select("tbody#station-list tr"):
                th = r.find("th")
                if th and "อินทร์บุรี" in th.get_text():
                    row = r
                    break

        if not row:
            print("❌ ไม่พบสถานีอินทร์บุรีในหน้าเว็บ")
            return None, None

        tds = row.find_all("td")
        level = tds[1].get_text(strip=True)
        bank  = tds[2].get_text(strip=True)
        print(f"✅ ข้อมูลระดับน้ำ: {level} ม., ตลิ่ง: {bank} ม.")
        return level, bank

    except Exception as e:
        print(f"❌ ERROR ดึงข้อมูลอินทร์บุรี: {e}")
        return None, None

# --- ฟังก์ชันดึงข้อมูลการปล่อยน้ำเขื่อนเจ้าพระยา ---
def fetch_chao_phraya_dam_discharge(url: str):
    try:
        headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
        res = requests.get(url, headers=headers, timeout=20)
        res.raise_for_status()

        matches = re.findall(r"parseFloat\('([0-9.]+)'\)", res.text)
        if matches:
            discharge = matches[-1]
            print(f"✅ ปริมาณน้ำไหลผ่านเขื่อนเจ้าพระยา: {discharge}")
            return discharge
        else:
            print("❌ ไม่พบข้อมูลการปล่อยน้ำใน Script จากเว็บ")
            return None
    except Exception as e:
        print(f"❌ ERROR: เกิดข้อผิดพลาดในการดึงข้อมูลเขื่อน: {e}")
        return None

# --- ฟังก์ชันโหลดข้อมูลย้อนหลัง ---
def load_historical_data(file_path: str):
    try:
        df = pd.read_csv(file_path)
        df['เดือน'] = df['เดือน'].str.strip().map(THAI_MONTH_MAP)
        df['ปี'] = df['ปี'] - 543
        df['date'] = pd.to_datetime(
            df[['ปี', 'เดือน', 'วันที่']].rename(
                columns={'ปี': 'year', 'เดือน': 'month', 'วันที่': 'day'}
            )
        )
        return df
    except FileNotFoundError:
        print(f"❌ ERROR: ไม่พบไฟล์ข้อมูลย้อนหลังที่: {file_path}")
        return None
    except Exception as e:
        print(f"❌ ERROR: เกิดข้อผิดพลาดในการโหลดข้อมูลย้อนหลัง: {e}")
        return None

# --- ฟังก์ชันค้นหาข้อมูลย้อนหลังวันเดียวกัน ---
def find_historical_discharge(df, target_date):
    if df is None:
        return "ไม่มีข้อมูล"
    try:
        match = df[df['date'].dt.strftime('%m-%d') == target_date.strftime('%m-%d')]
        return match['ปริมาณน้ำ (ลบ.ม./วินาที)'].iloc[-1] if not match.empty else "ไม่มีข้อมูล"
    except Exception:
        return "หาข้อมูลไม่ได้"

# --- ฟังก์ชันสร้างและส่งข้อความ ---
def analyze_and_create_message(current_level, current_discharge, bank_level, hist_2024, hist_2011):
    today_th = datetime.now(pytz.timezone('Asia/Bangkok')).strftime('%d %B %Y %H:%M')
    status = "❌ ไม่สามารถประมวลผลข้อมูลระดับน้ำได้"
    remaining_str = "N/A"
    try:
        level_f = float(current_level)
        bank_f  = float(bank_level)
        rem = bank_f - level_f
        remaining_str = f"{rem:.2f}"
        if level_f >= bank_f:
            status = "🚨 ระดับน้ำถึงตลิ่งแล้ว! 🚨"
        elif rem <= 1.0:
            status = "❗❗ แจ้งเตือนระดับน้ำใกล้ถึงตลิ่ง ❗❗"
        elif rem <= 2.0:
            status = "⚠️ แจ้งเตือนระดับน้ำ"
        else:
            status = "💧 สถานการณ์น้ำปกติ"
    except (ValueError, TypeError):
        pass

    message = (
        f"📢 สรุปสถานการณ์น้ำ {today_th} (GMT+7)\n"
        f"=========================\n"
        f"🌊 **สถานี C.2 อ.เมืองสิงห์บุรี**\n"
        f"   - ระดับน้ำ: **{current_level} ม.** (รทก.)\n"
        f"   - ระดับตลิ่ง: **{bank_level} ม.** (รทก.)\n"
        f"   - ต่ำกว่าตลิ่ง: **{remaining_str} ม.**\n"
        f"   - สถานะ: {status}\n"
        f"=========================\n"
        f"댐 **เขื่อนเจ้าพระยา (C.13)**\n"
        f"   - ปริมาณน้ำไหลผ่าน (ล่าสุด):\n"
        f"     **{current_discharge} ลบ.ม./วินาที**\n\n"
        f"   - **เปรียบเทียบข้อมูลย้อนหลัง (วันเดียวกัน):**\n"
        f"     - ปี 2567 (2024): **{hist_2024}** ลบ.ม./วินาที\n"
        f"     - ปี 2554 (2011): **{hist_2011}** ลบ.ม./วินาที\n"
        f"=========================\n"
        f"#แจ้งเตือนน้ำสิงห์บุรี #เขื่อนเจ้าพระยา"
    )
    return message.strip()

# --- ฟังก์ชันส่ง LINE Broadcast ---
def send_line_broadcast(message):
    if not LINE_TOKEN:
        print("❌ ERROR: ไม่ได้ตั้งค่า LINE_CHANNEL_ACCESS_TOKEN")
        return
    headers = {"Authorization": f"Bearer {LINE_TOKEN}"}
    payload = {"messages": [{"type": "text", "text": message}]}
    try:
        res = requests.post(LINE_API_URL, headers=headers, json=payload, timeout=10)
        res.raise_for_status()
        print("✅ ส่งข้อความ Broadcast สำเร็จ!")
    except Exception as e:
        print(f"❌ ERROR: LINE Broadcast: {e} | Response: {res.text if 'res' in locals() else 'N/A'}")

# --- Main ---
if __name__ == "__main__":
    print("=== เริ่มการทำงานระบบแจ้งเตือนน้ำอินทร์บุรี ===")
    inburi_level, bank_level = get_inburi_data(SINGBURI_URL)
    dam_discharge = fetch_chao_phraya_dam_discharge(DISCHARGE_URL)
    historical_df = load_historical_data(HISTORICAL_DATA_FILE)

    today = datetime.now(pytz.timezone('Asia/Bangkok'))
    target_date_2024 = today.replace(year=2024)
    target_date_2011 = today.replace(year=2011)

    hist_2567 = find_historical_discharge(historical_df, target_date_2024)
    hist_2554 = find_historical_discharge(historical_df, target_date_2011)

    if inburi_level and bank_level and dam_discharge:
        final_message = analyze_and_create_message(
            inburi_level, dam_discharge, bank_level, hist_2567, hist_2554
        )
        print("\n--- ข้อความที่จะส่ง ---\n" + final_message + "\n--------------------\n")
        send_line_broadcast(final_message)
    else:
        print("❌ เกิดข้อผิดพลาดในการดึงข้อมูลบางส่วน ไม่สามารถส่งแจ้งเตือนได้")
