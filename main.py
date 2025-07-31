import pandas as pd
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import re # For regular expressions to extract numbers

# --- User Configuration ---
# ใส่ LINE Notify Token ของคุณที่นี่
LINE_NOTIFY_TOKEN = "YOUR_LINE_NOTIFY_TOKEN" # <<<<<<< สำคัญ: โปรดเปลี่ยนค่านี้เป็น Token ของคุณจริงๆ
WEB_URL = "https://tiwrm.hii.or.th/DATA/REPORT/php/chart/chaopraya/small/chaopraya.php"
HISTORY_FILE = "dam_discharge_history_complete.csv" # ตรวจสอบให้แน่ใจว่าไฟล์นี้อยู่ในที่เดียวกับ script

# --- Helper Functions ---
def thai_month_to_int(month_thai):
    """Converts Thai month name to its corresponding integer (1-12) without locale."""
    month_map = {
        'มกราคม': 1, 'กุมภาพันธ์': 2, 'มีนาคม': 3, 'เมษายน': 4,
        'พฤษภาคม': 5, 'มิถุนายน': 6, 'กรกฎาคม': 7, 'สิงหาคม': 8,
        'กันยายน': 9, 'ตุลาคม': 10, 'พฤศจิกายน': 11, 'ธันวาคม': 12
    }
    return month_map.get(month_thai, None)

def load_and_preprocess_history_data(file_path):
    """
    Loads CSV history data, preprocesses it by converting Thai month to int,
    combining date columns, and setting 'date' as index.
    """
    df = pd.read_csv(file_path)
    df.columns = ['day', 'month_thai', 'year', 'discharge_m3_per_s']
    df['month'] = df['month_thai'].apply(thai_month_to_int)
    df['year'] = df['year'].apply(lambda x: x - 543 if x > 2400 else x) # Convert BE to CE
    df['date'] = pd.to_datetime(df[['year', 'month', 'day']], errors='coerce')
    df.dropna(subset=['date'], inplace=True)
    df.set_index('date', inplace=True)
    return df[['discharge_m3_per_s']]

def get_live_discharge_from_web(url):
    """
    Fetches live discharge data from the specified web URL, targeting '1,050.00'.
    Returns the discharge value (float) and current date (datetime object).
    Returns None, None if data cannot be fetched or parsed.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the <td> tag that contains the text 'ปริมาณน้ำ'
        discharge_label_td = soup.find('td', string='ปริมาณน้ำ')

        if discharge_label_td:
            # Find the next sibling <td> which contains the value
            # It has class 'text_bold' and colspan='2'
            discharge_value_td = discharge_label_td.find_next_sibling('td', class_='text_bold', colspan='2')

            if discharge_value_td:
                # Extract the entire text content, e.g., '1,050.00/ 2840 cms'
                full_text = discharge_value_td.get_text(strip=True)
                # Use regex to extract the first number, allowing commas and decimals
                # The pattern r'([\d,\.]+)' will capture '1,050.00'
                match = re.search(r'([\d,\.]+)', full_text)
                if match:
                    discharge_str = match.group(1).replace(',', '') # Remove comma for conversion
                    live_discharge = float(discharge_str)
                    live_date = datetime.now() # Get current date for the live data
                    return live_discharge, live_date
                else:
                    print(f"ไม่พบรูปแบบตัวเลขที่ต้องการ (เช่น 1,050.00) ในข้อความ: '{full_text}'")
            else:
                print("ไม่พบแท็ก <td> ที่มีค่าปริมาณน้ำ (sibling of 'ปริมาณน้ำ' with class='text_bold' and colspan='2')")
        else:
            print("ไม่พบแท็ก <td> ที่มีข้อความ 'ปริมาณน้ำ'")

    except requests.exceptions.RequestException as e:
        print(f"เกิดข้อผิดพลาดในการเชื่อมต่อหน้าเว็บ: {e}")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงหรือวิเคราะห์ข้อมูลจากหน้าเว็บ: {e}")
    return None, None

def send_line_notification(message, token):
    """Sends a notification message to LINE Notify."""
    if not token or token == "YOUR_LINE_NOTIFY_TOKEN":
        print("ยังไม่ได้ตั้งค่า LINE Notify Token. ไม่สามารถส่งข้อความได้.")
        return

    url = "https://notify-api.line.me/api/notify"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "message": message
    }
    try:
        response = requests.post(url, headers=headers, data=payload)
        response.raise_for_status() # Raise an exception for HTTP errors
        print(f"ส่ง LINE Notification สำเร็จ: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"เกิดข้อผิดพลาดในการส่ง LINE Notification: {e}")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดที่ไม่คาดคิดในการส่ง LINE Notification: {e}")

# --- Main Logic ---
if __name__ == "__main__":
    print("กำลังเริ่มต้นดึงข้อมูลและเตรียมการแจ้งเตือน...")

    # 1. ดึงข้อมูลสดใหม่จากหน้าเว็บ
    live_discharge, live_date = get_live_discharge_from_web(WEB_URL)

    if live_discharge is None:
        print("ไม่สามารถดึงข้อมูลปริมาณน้ำล่าสุดได้. จบการทำงาน.")
        send_line_notification("แจ้งเตือนสถานการณ์น้ำ: ไม่สามารถดึงข้อมูลล่าสุดจากหน้าเว็บได้", LINE_NOTIFY_TOKEN)
        # We don't exit here immediately, still try to send notification
        # Consider if you want to exit or continue with partial information
        exit() # Exit if live data is not available

    # Format live date to Buddhist Era for display
    live_date_be_str = f"{live_date.day:02d} {live_date.strftime('%B')} {live_date.year + 543} พ.ศ."
    live_year_be = live_date.year + 543
    live_month_day = live_date.strftime('%m-%d') # Format for comparison (e.g., '07-31')

    print(f"ข้อมูลปริมาณน้ำล่าสุด (จากหน้าเว็บ): {live_discharge:.2f} ลบ.ม./วินาที ณ วันที่ {live_date_be_str}") # Changed to .2f for 1050.00

    # 2. โหลดและเตรียมข้อมูลย้อนหลัง
    history_data = load_and_preprocess_history_data(HISTORY_FILE)
    history_data['month_day'] = history_data.index.strftime('%m-%d') # Add month_day for easy lookup

    # 3. ดึงข้อมูลย้อนหลังสำหรับวันเดียวกัน
    discharge_2567 = None
    discharge_2554 = None

    # Get data for the current month-day in 2024 (2567 BE)
    current_day_2024_data = history_data[(history_data['year'] == 2024) & (history_data['month_day'] == live_month_day)]
    if not current_day_2024_data.empty:
        discharge_2567 = current_day_2024_data['discharge_m3_per_s'].iloc[0]

    # Get data for the current month-day in 2011 (2554 BE)
    current_day_2011_data = history_data[(history_data['year'] == 2011) & (history_data['month_day'] == live_month_day)]
    if not current_day_2011_data.empty:
        discharge_2554 = current_day_2011_data['discharge_m3_per_s'].iloc[0]

    # 4. สร้างข้อความแจ้งเตือน
    notification_message = f"📢 แจ้งเตือนปริมาณน้ำท้ายเขื่อนเจ้าพระยา (อัปเดต):\n"
    notification_message += f"ปี {live_year_be} (ล่าสุด ณ {live_date_be_str}): {live_discharge:.2f} ลบ.ม./วินาที\n"

    if discharge_2567 is not None:
        notification_message += f"เทียบกับปี 2567 ({live_date.strftime('%d %B')} 2567): {discharge_2567:.0f} ลบ.ม./วินาที\n"
    else:
        notification_message += f"เทียบกับปี 2567 ({live_date.strftime('%d %B')} 2567): ไม่มีข้อมูลย้อนหลัง\n"

    if discharge_2554 is not None:
        notification_message += f"เทียบกับปี 2554 ({live_date.strftime('%d %B')} 2554): {discharge_2554:.0f} ลบ.ม./วินาที\n"
    else:
        notification_message += f"เทียบกับปี 2554 ({live_date.strftime('%d %B')} 2554): ไม่มีข้อมูลย้อนหลัง\n"

    # Optional: Add a simple comparison alert within the message
    if discharge_2567 is not None and live_discharge is not None:
        diff_2567 = live_discharge - discharge_2567
        if diff_2567 > 0:
            notification_message += f"  (สูงกว่าปี 2567: {abs(diff_2567):.2f} ลบ.ม./วินาที)\n"
        elif diff_2567 < 0:
            notification_message += f"  (ต่ำกว่าปี 2567: {abs(diff_2567):.2f} ลบ.ม./วินาที)\n"

    if discharge_2554 is not None and live_discharge is not None:
        diff_2554 = live_discharge - discharge_2554
        if diff_2554 > 0:
            notification_message += f"  (สูงกว่าปี 2554: {abs(diff_2554):.2f} ลบ.ม./วินาที)\n"
        elif diff_2554 < 0:
            notification_message += f"  (ต่ำกว่าปี 2554: {abs(diff_2554):.2f} ลบ.ม./วินาที)\n"

    print("\n--- ข้อความที่จะส่งไปยัง LINE ---")
    print(notification_message)

    # 5. ส่งแจ้งเตือนผ่าน LINE Notify
    send_line_notification(notification_message, LINE_NOTIFY_TOKEN)

    print("\nดำเนินการเสร็จสิ้น.")
