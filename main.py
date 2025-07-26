import requests
import os
from datetime import datetime
import pytz
from bs4 import BeautifulSoup

SINGBURI_WATER_URL = "https://singburi.thaiwater.net/wl"
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"

def get_singburi_data(url):
    """ดึงระดับน้ำจากเว็บ singburi.thaiwater.net สำหรับสถานี 'อินทร์บุรี' (DOM ใหม่ มี <a> ซ้อนใน <th>)"""
    try:
        print("กำลังเชื่อมต่อกับ singburi.thaiwater.net...")
        response = requests.get(url, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.find_all("tr", class_="jss117 jss119")
        for row in rows:
            th = row.find("th")
            a_tag = th.find("a") if th else None
            if a_tag and "อินทร์บุรี" in a_tag.text:
                print("✅ พบข้อมูลของ 'อินทร์บุรี'")
                tds = row.find_all("td")
                if len(tds) >= 3:
                    level_str = tds[2].text.strip()
                    water_level = float(level_str)
                    print(f"ระดับน้ำอินทร์บุรี = {water_level} ม.รทก.")
                    return water_level
                else:
                    print("⚠️ พบแถวอินทร์บุรีแต่ข้อมูลไม่ครบ")
        print("❌ ไม่พบข้อมูลของ 'อินทร์บุรี' ในหน้าเว็บ")
        return None

    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
        return None

def get_dam_discharge_from_file():
    try:
        print("กำลังอ่านข้อมูลเขื่อนจากไฟล์ dam_data.txt...")
        with open('dam_data.txt', 'r') as f:
            discharge_rate = float(f.read().strip())
        print(f"เขื่อนระบายน้ำ {discharge_rate} ลบ.ม./วินาที")
        return discharge_rate
    except FileNotFoundError:
        print("⚠️ ไม่พบไฟล์ dam_data.txt! ใช้ค่า default = 1000 ลบ.ม./วินาที")
        return 1000
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการอ่านไฟล์ dam_data.txt: {e}")
        return 1000

def analyze_and_create_message(inburi_level, dam_discharge):
    if inburi_level is None:
        return "เกิดข้อผิดพลาด: ไม่สามารถดึงข้อมูลระดับน้ำอินทร์บุรีได้ กรุณาตรวจสอบเว็บไซต์ singburi.thaiwater.net"

    bank_height = 13.0
    distance_to_bank = bank_height - inburi_level

    if dam_discharge > 2400 or distance_to_bank < 1.0:
        status_emoji = "🟥"
        status_title = "‼️ ประกาศเตือนภัยระดับสูงสุด ‼️"
        recommendation = """คำแนะนำ:
1. เตรียมพร้อมอพยพหากอยู่ในพื้นที่เสี่ยง
2. ขนย้ายทรัพย์สินขึ้นที่สูงโดยด่วน
3. งดใช้เส้นทางสัญจรริมแม่น้ำ"""
    elif dam_discharge > 1800 or distance_to_bank < 2.0:
        status_emoji = "🟨"
        status_title = "‼️ ประกาศเฝ้าระวัง ‼️"
        recommendation = """คำแนะนำ:
1. บ้านเรือนริมตลิ่งนอกคันกั้นน้ำ ให้เริ่มขนของขึ้นที่สูง
2. ติดตามสถานการณ์อย่างใกล้ชิด"""
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
        f"  (ต่ำกว่าตลิ่ง {distance_to_bank:.2f} ม.)\n"
        f"• เขื่อนเจ้าพระยา (ล่าสุด): {dam_discharge:,.0f} ลบ.ม./วินาที\n\n"
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
    print("===== เริ่มการทำงานของระบบเฝ้าระวังน้ำ v4.0 (DOM ใหม่) =====")
    inburi_level = get_singburi_data(SINGBURI_WATER_URL)
    dam_discharge = get_dam_discharge_from_file()
    final_message = analyze_and_create_message(inburi_level, dam_discharge)
    print("\n--- ข้อความที่จะส่ง ---")
    print(final_message)
    print("-------------------------\n")
    send_line_broadcast(final_message)
    print("===== การทำงานเสร็จสิ้น =====")
