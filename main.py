import requests
import os
from datetime import datetime
import pytz

# --- ส่วนตั้งค่าหลัก ---
# URL สำหรับดึงข้อมูล
INBURI_URL = "http://watertele.rid.go.th/tele/lpbr_tele/report_hist.php?id=35"
CHAO_PHRAYA_DAM_URL = "https://watertele.rid.go.th/tele/dam/report_hist_dam.php?id=1"

# กุญแจสำหรับส่ง LINE
LINE_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_API_URL = "https://api.line.me/v2/bot/message/broadcast"

# *** เพิ่มส่วนนี้เข้ามา: ปิดการแจ้งเตือนเรื่อง SSL InsecureRequestWarning ***
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# --- ส่วนที่ 1: ฟังก์ชันดึงข้อมูล (Web Scraping) ---
def get_water_data(url):
    """ดึงข้อมูลจากเว็บกรมชลประทานและคืนค่าล่าสุด"""
    try:
        # *** แก้ไขตรงนี้: เพิ่ม verify=False เพื่อข้ามการตรวจสอบ SSL ***
        response = requests.get(url, timeout=15, verify=False)
        response.raise_for_status()
        
        last_row = response.text.split('</TR>')[-2]
        columns = last_row.split('</TD>')
        
        timestamp_str = columns[0].split('>')[-1].strip()
        water_level = float(columns[1].split('>')[-1].strip())
        flow_rate = float(columns[2].split('>')[-1].strip())
        
        return timestamp_str, water_level, flow_rate
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลจาก {url}: {e}")
        return None, None, None

def get_dam_data(url):
    """ดึงข้อมูลจากเว็บเขื่อน"""
    try:
        # *** แก้ไขตรงนี้: เพิ่ม verify=False เพื่อข้ามการตรวจสอบ SSL ***
        response = requests.get(url, timeout=15, verify=False)
        response.raise_for_status()
        last_row = response.text.split('</TR>')[-2]
        columns = last_row.split('</TD>')
        
        discharge_rate = float(columns[6].split('>')[-1].strip())
        return discharge_rate
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูลเขื่อนจาก {url}: {e}")
        return None

# --- ส่วนที่ 2: ฟังก์ชันวิเคราะห์และสร้างข้อความ (เหมือนเดิม) ---
def analyze_and_create_message(inburi_level, dam_discharge):
    """วิเคราะห์ข้อมูลและสร้างข้อความสำหรับส่ง LINE"""
    if inburi_level is None or dam_discharge is None:
        return "เกิดข้อผิดพลาด: ไม่สามารถดึงข้อมูลน้ำเพื่อทำการวิเคราะห์ได้"

    distance_to_bank = 12.45 - inburi_level
    
    if dam_discharge > 2400 or distance_to_bank < 1.0:
        status_emoji = "🟥"
        status_title = "‼️ ประกาศเตือนภัยระดับสูงสุด ‼️"
        recommendation = (
            "คำแนะนำ:\n"
            "1. เตรียมพร้อมอพยพหากอยู่ในพื้นที่เสี่ยง\n"
            "2. ขนย้ายทรัพย์สินขึ้นที่สูงโดยด่วน\n"
            "3. งดใช้เส้นทางสัญจรริมแม่น้ำ"
        )
    elif dam_discharge > 1800 or distance_to_bank < 2.0:
        status_emoji = "🟨"
        status_title = "‼️ ประกาศเฝ้าระวัง ‼️"
        recommendation = (
            "คำแนะนำ:\n"
            "1. บ้านเรือนริมตลิ่งนอกคันกั้นน้ำ ให้เริ่มขนของขึ้นที่สูง\n"
            "2. ติดตามสถานการณ์อย่างใกล้ชิด"
        )
    else:
        status_emoji = "🟩"
        status_title = "สถานะปกติ"
        recommendation = "สรุป: สถานการณ์น้ำยังปกติ ไม่น่ากังวล ขอให้ประชาชนใช้ชีวิตได้ตามปกติครับ"

    tz = pytz.timezone('Asia/Bangkok')
    now = datetime.now(tz)
    
    message = (
        f"{status_emoji} {status_title}\n"
        f"รายงานสถานการณ์น้ำเจ้าพระยา อ.อินทร์บุรี\n"
        f"ประจำวันที่: {now.strftime('%d/%m/%Y %H:%M')} น.\n\n"
        f"• ระดับน้ำ (C.35 อินทร์บุรี): {inburi_level:.2f} ม.รทก.\n"
        f"  (ต่ำกว่าตลิ่ง {distance_to_bank:.2f} ม.)\n"
        f"• เขื่อนเจ้าพระยา: ระบายน้ำ {dam_discharge:,.0f} ลบ.ม./วินาที\n\n"
        f"{recommendation}"
    )
    return message

# --- ส่วนที่ 3: ฟังก์ชันส่งข้อความไปที่ LINE (เหมือนเดิม) ---
def send_line_broadcast(message):
    """ส่งข้อความไปยังผู้ติดตาม LINE OA ทั้งหมด"""
    if not LINE_TOKEN:
        print("ไม่พบ LINE_CHANNEL_ACCESS_TOKEN")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    payload = {
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    try:
        response = requests.post(LINE_API_URL, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print("ส่งข้อความ Broadcast สำเร็จ!")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการส่ง LINE Broadcast: {e}")

# --- ส่วนทำงานหลัก (Main) (เหมือนเดิม) ---
if __name__ == "__main__":
    print("===== เริ่มการทำงานของระบบเฝ้าระวังน้ำ =====")
    
    print("กำลังดึงข้อมูลระดับน้ำอินทร์บุรี...")
    inburi_time, inburi_level, inburi_flow = get_water_data(INBURI_URL)
    
    print("กำลังดึงข้อมูลการระบายน้ำเขื่อนเจ้าพระยา...")
    dam_discharge = get_dam_data(CHAO_PHRAYA_DAM_URL)
    
    if inburi_level and dam_discharge:
        print(f"ข้อมูลล่าสุด: ระดับน้ำอินทร์บุรี {inburi_level:.2f} ม., เขื่อนระบาย {dam_discharge:,.0f} ลบ.ม./วินาที")
        
        final_message = analyze_and_create_message(inburi_level, dam_discharge)
        print("\n--- ข้อความที่จะส่ง ---")
        print(final_message)
        print("---------------------\n")
        
        send_line_broadcast(final_message)
        
    else:
        print("ไม่สามารถดึงข้อมูลสำคัญได้ ระบบจึงไม่ทำการส่งข้อความ")
        
    print("===== การทำงานเสร็จสิ้น =====")
