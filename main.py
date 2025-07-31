import requests
import os
from datetime import datetime
import pandas as pd
import pytz
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
import re
import time

# --- URL ที่อัปเดตใหม่ตามที่คุณระบุ ---
# แหล่งข้อมูลระดับน้ำ อ.อินทร์บุรี (เว็บใหม่)
INBURI_WATER_URL = "https://singburi.thaiwater.net/wl"
# แหล่งข้อมูลการระบายน้ำเขื่อนเจ้าพระยา (ยังคงเดิม)
DISCHARGE_URL = "https://www.thaiwater.net/water/dam/large"

# --- ค่าคงที่และ Token ---
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"
HISTORICAL_EXCEL_PATH = "data/dam_discharge_history.xlsx"

def get_inburi_bridge_level():
    """
    ดึงข้อมูลระดับน้ำที่สถานีอินทร์บุรี (จาก singburi.thaiwater.net/wl)
    โดยใช้ Selenium เพื่อดึงข้อมูลจากหน้าเว็บที่โหลดด้วย JavaScript
    """
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

        print("กำลังเริ่มต้น ChromeDriver...")
        driver = webdriver.Chrome(service=ChromeService(), options=options)
        driver.set_page_load_timeout(180)
        print(f"กำลังเข้าถึง URL: {INBURI_WATER_URL}")
        driver.get(INBURI_WATER_URL)
        print("เข้าถึง URL สำเร็จแล้ว กำลังรอการโหลดข้อมูล...")

        # === จุดที่แก้ไข: รอจนกว่าแถวของ "อินทร์บุรี" จะปรากฏขึ้น และดึงข้อมูลจากเซลล์ที่ถูกต้อง ===
        wait = WebDriverWait(driver, 60)
        
        # ใช้ XPath เพื่อหาแถว (tr) ที่มี header (th) ที่มีข้อความว่า "อินทร์บุรี"
        inburi_row_xpath = "//th[contains(text(), 'อินทร์บุรี')]/ancestor::tr"
        inburi_row = wait.until(EC.presence_of_element_located((By.XPATH, inburi_row_xpath)))
        print("พบแถวข้อมูลของ 'อินทร์บุรี' แล้ว")

        # จากโครงสร้าง HTML ใหม่:
        # <td> แรก (index 0) คือ ที่ตั้ง
        # <td> ที่สอง (index 1) คือ ระดับน้ำที่เราต้องการ
        cells = inburi_row.find_elements(By.TAG_NAME, "td")
        
        if len(cells) > 1:
            level_str = cells[1].text.strip()
            print(f"พบระดับน้ำสำหรับสถานีอินทร์บุรี: {level_str}")
            return float(level_str)
        else:
            print("ไม่พบเซลล์ข้อมูลระดับน้ำในแถวของอินทร์บุรี")
            return None

    except Exception as e:
        print(f"❌ ERROR: get_inburi_bridge_level: {e}")
        return None
    finally:
        if driver:
            print("กำลังปิด ChromeDriver...")
            driver.quit()

def fetch_chao_phraya_dam_discharge():
    """
    ดึงข้อมูลการระบายน้ำท้ายเขื่อนเจ้าพระยา
    โดยใช้ BeautifulSoup
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                   "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
                   "Cache-Control": "no-cache",
                   "Pragma": "no-cache"}
        res = requests.get(DISCHARGE_URL, headers=headers, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'html.parser')

        tables = soup.find_all('table', class_='table-bordered')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) > 1 and "เขื่อนเจ้าพระยา" in cells[1].text:
                    if len(cells) > 6:
                        discharge_text = cells[6].text.strip().replace(',', '')
                        return float(discharge_text)
        return None
    except Exception as e:
        print(f"❌ ERROR: fetch_chao_phraya_dam_discharge: {e}")
        return None


def get_history_discharge():
    """
    คืนค่า dict {ปี: ปริมาณน้ำ} เฉพาะปีปัจจุบัน กับ 2554
    """
    try:
        now = datetime.now(pytz.timezone("Asia/Bangkok"))
        current_year_th = now.year + 543
        day = now.day
        month_en = now.strftime("%B")
        month_map = {
            "January": "มกราคม", "February": "กุมภาพันธ์", "March": "มีนาคม",
            "April": "เมษายน", "May": "พฤษภาคม", "June": "มิถุนายน",
            "July": "กรกฎาคม", "August": "สิงหาคม", "September": "กันยายน",
            "October": "ตุลาคม", "November": "พฤศจิกายน", "December": "ธันวาคม"
        }
        month_th = month_map[month_en]

        df = pd.read_excel(HISTORICAL_EXCEL_PATH)

        years_check = [current_year_th - 1, 2554]
        result = {}
        for year_th in years_check:
            match = df[
                (df["วันที่"] == day) &
                (df["เดือน"] == month_th) &
                (df["ปี"] == year_th)
            ]
            if not match.empty:
                result[year_th] = match["ปริมาณน้ำ (ลบ.ม./วิ)"].values[0]

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

    bank_height = 13.0 
    history = get_history_discharge()
    prev_discharge_text = ""
    if history:
        prev_discharge_text += "ข้อมูลน้ำในวันเดียวกัน:\n"
        if history.get(max(history.keys())):
             prev_discharge_text += f"• ปีที่แล้ว: {history[max(history.keys())]:,.0f} ลบ.ม./วินาที\n"
        if history.get(2554):
             prev_discharge_text += f"• ปี 2554: {history[2554]:,.0f} ลบ.ม./วินาที\n"

    distance_to_bank = bank_height - inburi_level
    if dam_discharge > 2400 or distance_to_bank < 1.0:
        status_emoji = "🟥"
        status_title = "‼️ ประกาศเตือนภัยระดับสูงสุด ‼️"
        recommendation = "คำแนะนำ:\n1. โปรดเตรียมความพร้อมเคลื่อนย้ายหากอยู่ในพื้นที่เสี่ยง\n2. ควรย้ายทรัพย์สินและของใช้จำเป็นขึ้นที่สูง\n3. โปรดระมัดระวังการใช้เส้นทางสัญจรริมแม่น้ำ"
    elif dam_discharge > 1800 or distance_to_bank < 2.0:
        status_emoji = "🟨"
        status_title = "‼️ ประกาศเฝ้าระวัง ‼️"
        watch_recommendations = [
            "คำแนะนำ:\n1. บ้านเรือนริมตลิ่งนอกคันกั้นน้ำ ควรเตรียมขนของขึ้นที่สูง\n2. ขอให้ติดตามสถานการณ์อย่างใกล้ชิด",
            "คำแนะนำ:\n1. ควรเก็บเอกสารสำคัญและของมีค่าไว้ในที่ปลอดภัยและกันน้ำได้\n2. ติดตามข่าวสารจากหน่วยงานราชการ",
            "คำแนะนำ:\n1. ควรเตรียมชุดอุปกรณ์ฉุกเฉิน เช่น ไฟฉาย ยา และอาหารแห้ง\n2. วางแผนเส้นทางที่ปลอดภัยหากต้องย้าย",
            "คำแนะนำ:\n1. โปรดตรวจสอบและให้ความช่วยเหลือเด็ก ผู้สูงอายุ หรือผู้ป่วยในบ้าน\n2. งดวางสิ่งของกีดขวางทางระบายน้ำ"
        ]
        recommendation = random.choice(watch_recommendations)
    else:
        status_emoji = "🟩"
        status_title = "สถานะปกติ"
        recommendation = "สถานการณ์น้ำยังคงปกติ สามารถใช้ชีวิตได้ตามปกติครับ"

    now = datetime.now(pytz.timezone("Asia/Bangkok"))
    message = f"""{status_emoji} {status_title}
รายงานสถานการณ์น้ำเจ้าพระยา อ.อินทร์บุรี
ประจำวันที่: {now.strftime("%d/%m/%Y %H:%M")} น.

• ระดับน้ำ (สะพานอินทร์บุรี): {inburi_level:.2f} ม.รทก.
  (ต่ำกว่าตลิ่งประมาณ {distance_to_bank:.2f} ม.)
• เขื่อนเจ้าพระยา (ระบายท้ายเขื่อน): {dam_discharge:,.0f} ลบ.ม./วินาที

{prev_discharge_text}
-----------------------------------
{recommendation}"""
    return message

def send_line_broadcast(message):
    """
    ส่งข้อความแจ้งเตือนผ่าน LINE Broadcast
    """
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

if __name__ == "__main__":
    print("=== เริ่มการทำงานระบบแจ้งเตือนน้ำอินทร์บุรี (เวอร์ชันปรับปรุง) ===")

    inburi_level = get_inburi_bridge_level()
    dam_discharge = fetch_chao_phraya_dam_discharge()

    if dam_discharge is None:
        dam_discharge = 0 

    final_message = analyze_and_create_message(inburi_level, dam_discharge)

    print("\n📤 ข้อความที่จะแจ้งเตือน:")
    print(final_message)
    print("\n🚀 กำลังส่งข้อความไปยัง LINE...")
    send_line_broadcast(final_message)
    print("✅ เสร็จสิ้นการทำงาน")
