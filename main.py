import requests
import os
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# --- ค่าคงที่ ---
SINGBURI_WATER_URL = "https://singburi.thaiwater.net/wl"
DISCHARGE_URL = "https://tiwrm.hii.or.th/DATA/REPORT/php/chart/chaopraya/small/chaopraya.php"
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"


# --- ดึงระดับน้ำอินทร์บุรี (Updated with better camouflage and screenshot debugging) ---
def get_singburi_data(url):
    """
    ดึงข้อมูลจากเว็บ singburi.thaiwater.net โดยใช้ Playwright
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # สร้าง Context ให้เหมือนเบราว์เซอร์จริงมากขึ้น
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=120000)
            page.wait_for_selector("div[aria-labelledby='waterLevel'] table tr", timeout=60000)
            
            html = page.content()
            browser.close()

            soup = BeautifulSoup(html, 'html.parser')
            water_table = soup.find("div", attrs={"aria-labelledby": "waterLevel"})
            if not water_table:
                return None, None
            
            rows = water_table.find_all("tr")
            for row in rows:
                station_header = row.find("th")
                if station_header and "อินทร์บุรี" in station_header.get_text(strip=True):
                    tds = row.find_all("td")
                    if len(tds) > 2:
                        level_str = tds[1].text.strip()
                        bank_level_str = tds[2].text.strip()
                        print(f"✅ พบข้อมูลอินทร์บุรี: ระดับน้ำ={level_str}, ระดับตลิ่ง={bank_level_str}")
                        return float(level_str), float(bank_level_str)
            return None, None
        except Exception as e:
            print(f"❌ ERROR: get_singburi_data: {e}")
            # ถ่าย Screenshot ตอนที่เกิด Error เพื่อการดีบัก
            page.screenshot(path='debug_screenshot.png')
            print("📸 Screenshot 'debug_screenshot.png' saved for debugging.")
            browser.close()
            return None, None


# --- ดึงข้อมูล discharge จากเว็บ HII ---
def fetch_chao_phraya_dam_discharge():
    """
    ดึงข้อมูลจากเว็บ tiwrm.hii.or.th
    """
    try:
        res = requests.get(DISCHARGE_URL, timeout=30)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')

        header_cell = soup.find(lambda tag: tag.name == 'td' and 'ปริมาณน้ำ' in tag.text)
        if header_cell:
            value_cell = header_cell.find_next_sibling('td')
            if value_cell:
                full_text = value_cell.text.strip()
                discharge_str = full_text.split('/')[0]
                discharge_value = float(discharge_str.replace(',', ''))
                print(f"✅ พบข้อมูลเขื่อนเจ้าพระยา: {discharge_value}")
                return discharge_value

        print("⚠️ ไม่พบข้อมูล 'ท้ายเขื่อนเจ้าพระยา' ในหน้าเว็บ (โครงสร้างอาจไม่ตรง)")
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
    if inburi_level is not None and bank_level is not None and dam_discharge is not None:
        print("✅ ดึงข้อมูลสำเร็จทั้งหมด กำลังสร้างข้อความปกติ...")
        final_message = analyze_and_create_message(inburi_level, dam_discharge, bank_level)
    else:
        print("❌ ดึงข้อมูลไม่สำเร็จอย่างน้อย 1 รายการ กำลังสร้างข้อความแจ้งเตือนข้อผิดพลาด...")
        inburi_status = f"สำเร็จ (ระดับน้ำ={inburi_level}, ตลิ่ง={bank_level})" if inburi_level is not None else "ล้มเหลว"
        discharge_status = f"สำเร็จ ({dam_discharge:,.0f})" if dam_discharge is not None else "ล้มเหลว"
        final_message = create_error_message(inburi_status, discharge_status)

    print("\n📤 ข้อความที่จะแจ้งเตือน:")
    print(final_message)
    print("\n🚀 ส่งข้อความไปยัง LINE...")
    send_line_broadcast(final_message)
    print("✅ เสร็จสิ้นการทำงาน")
