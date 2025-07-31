import requests
import os
from datetime import datetime
import pandas as pd
import pytz
from bs4 import BeautifulSoup
import random

# --- Configuration ---
INBURI_WATER_URL = "https://singburi.thaiwater.net/wl"
DISCHARGE_URL = "https://www.thaiwater.net/water/dam/large"
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"
HISTORICAL_EXCEL_PATH = "data/dam_discharge_history.xlsx"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}


def get_inburi_bridge_level():
    """
    ดึงข้อมูลระดับน้ำที่สถานีอินทร์บุรี โดยใช้ BeautifulSoup
    """
    try:
        res = requests.get(INBURI_WATER_URL, headers=headers, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'html.parser')
        for row in soup.find_all('tr'):
            th = row.find('th', scope='row')
            if th and 'อินทร์บุรี' in th.get_text(strip=True):
                cells = row.find_all('td')
                if len(cells) >= 2:
                    level_str = cells[1].get_text(strip=True)
                    print(f"พบระดับน้ำสำหรับสถานีอินทร์บุรี: {level_str}")
                    return float(level_str)
        print("ไม่พบข้อมูลสถานีอินทร์บุรีในตาราง")
        return None
    except Exception as e:
        print(f"❌ ERROR: get_inburi_bridge_level: {e}")
        return None


def fetch_chao_phraya_dam_discharge():
    """
    ดึงข้อมูลการระบายน้ำท้ายเขื่อนเจ้าพระยา โดยใช้ BeautifulSoup
    """
    try:
        res = requests.get(DISCHARGE_URL, headers=headers, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'html.parser')
        for table in soup.find_all('table', class_='table-bordered'):
            for row in table.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) > 6 and 'เจ้าพระยา' in cells[1].get_text(strip=True):
                    discharge_text = cells[6].get_text(strip=True).replace(',', '')
                    print(f"พบการระบายน้ำของเขื่อนเจ้าพระยา: {discharge_text}")
                    return float(discharge_text)
        print("ไม่พบข้อมูลการระบายน้ำของเขื่อนเจ้าพระยา")
        return None
    except Exception as e:
        print(f"❌ ERROR: fetch_chao_phraya_dam_discharge: {e}")
        return None


def get_history_discharge():
    """
    คืนค่า dict {ปี: ปริมาณน้ำ} สำหรับปีที่แล้วและปี 2554
    """
    try:
        now = datetime.now(pytz.timezone("Asia/Bangkok"))
        year_th = now.year + 543
        day = now.day
        month_map = {
            "January": "มกราคม", "February": "กุมภาพันธ์", "March": "มีนาคม",
            "April": "เมษายน", "May": "พฤษภาคม", "June": "มิถุนายน",
            "July": "กรกฎาคม", "August": "สิงหาคม", "September": "กันยายน",
            "October": "ตุลาคม", "November": "พฤศจิกายน", "December": "ธันวาคม"
        }
        month_th = month_map[now.strftime("%B")]
        df = pd.read_excel(HISTORICAL_EXCEL_PATH)
        result = {}
        for y in [year_th - 1, 2554]:
            row = df[(df['วันที่']==day) & (df['เดือน']==month_th) & (df['ปี']==y)]
            if not row.empty:
                result[y] = row['ปริมาณน้ำ (ลบ.ม./วิ)'].iloc[0]
        return result
    except Exception as e:
        print(f"❌ ERROR: get_history_discharge: {e}")
        return {}


def analyze_and_create_message(inburi_level, dam_discharge):
    """
    วิเคราะห์ข้อมูลและสร้างข้อความแจ้งเตือน
    """
    if inburi_level is None or dam_discharge is None:
        return "เกิดข้อผิดพลาด: ไม่สามารถดึงข้อมูลสำคัญได้ครบถ้วน กรุณาตรวจสอบ Log"

    bank_height = 13.0  # ความสูงตลิ่ง อ.อินทร์บุรี
    history = get_history_discharge()
    prev_text = ""
    if history:
        prev_text = "ข้อมูลย้อนหลัง:\n"
        latest_year = max(history.keys())
        prev_text += f"• ปีที่แล้ว ({latest_year}): {history[latest_year]:,.0f} ลบ.ม./วินาที\n"
        if 2554 in history:
            prev_text += f"• ปี 2554: {history[2554]:,.0f} ลบ.ม./วินาที\n"

    distance = bank_height - inburi_level
    if dam_discharge > 2400 or distance < 1.0:
        emoji, title = "🟥", "‼️ ประกาศเตือนภัยระดับสูงสุด ‼️"
        rec = "1. เตรียมการเคลื่อนย้าย\n2. ย้ายทรัพย์สินขึ้นที่สูง\n3. ระวังเส้นทางริมแม่น้ำ"
    elif dam_discharge > 1800 or distance < 2.0:
        emoji, title = "🟨", "‼️ ประกาศเฝ้าระวัง ‼️"
        options = [
            "1. เก็บเอกสารสำคัญกันน้ำ\n2. ติดตามข่าวสาร",
            "1. เตรียมชุดอุปกรณ์ฉุกเฉิน\n2. วางแผนเส้นทางปลอดภัย",
            "1. ช่วยเหลือผู้สูงอายุเด็ก\n2. ไม่กีดขวางทางน้ำ"
        ]
        rec = random.choice(options)
    else:
        emoji, title = "🟩", "สถานะปกติ"
        rec = "สถานการณ์น้ำปกติ"

    now = datetime.now(pytz.timezone("Asia/Bangkok"))
    message = (
        f"{emoji} {title}\n"
        f"รายงานสถานการณ์น้ำ อ.อินทร์บุรี {now.strftime('%d/%m/%Y %H:%M')}\n"
        f"• ระดับน้ำ: {inburi_level:.2f} ม.รทก. (ห่างตลิ่ง {distance:.2f} ม.)\n"
        f"• ปริมาณน้ำเขื่อน: {dam_discharge:,.0f} ลบ.ม./วินาที\n"
        f"{prev_text}-----------------------------------\n{rec}"
    )
    return message


def send_line_broadcast(message):
    """
    ส่งข้อความแจ้งเตือนผ่าน LINE Broadcast
    """
    if not LINE_TOKEN:
        print("❌ ไม่พบ LINE_CHANNEL_ACCESS_TOKEN!")
        return
    headers_line = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    payload = {"messages": [{"type": "text", "text": message}]}
    try:
        res = requests.post(LINE_API_URL, headers=headers_line, json=payload, timeout=10)
        res.raise_for_status()
        print("✅ ส่งข้อความ Broadcast สำเร็จ!")
    except Exception as e:
        print(f"❌ ERROR: LINE Broadcast: {e}")


if __name__ == "__main__":
    print("=== เริ่มระบบแจ้งเตือนน้ำอินทร์บุรี ===")
    inburi_level = get_inburi_bridge_level()
    dam_discharge = fetch_chao_phraya_dam_discharge()
    if dam_discharge is None:
        dam_discharge = 0
    final_message = analyze_and_create_message(inburi_level, dam_discharge)
    print("ส่งข้อความ:\n", final_message)
    send_line_broadcast(final_message)
    print("✅ เสร็จสิ้นการทำงาน")
