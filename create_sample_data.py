import pandas as pd
import random
from datetime import datetime

# สร้างข้อมูลตัวอย่างสำหรับไฟล์ dam_discharge_history.xlsx
data = []

# สร้างข้อมูลสำหรับปี 2554 และปีปัจจุบัน-1
months = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
          'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']

current_year = datetime.now().year + 543
years = [2554, current_year - 1]

for year in years:
    for month in months:
        # จำนวนวันในแต่ละเดือน (ประมาณ)
        days_in_month = 31 if month in ['มกราคม', 'มีนาคม', 'พฤษภาคม', 'กรกฎาคม', 'สิงหาคม', 'ตุลาคม', 'ธันวาคม'] else 30
        if month == 'กุมภาพันธ์':
            days_in_month = 28
            
        for day in range(1, days_in_month + 1):
            # สร้างข้อมูลปริมาณน้ำแบบสุ่ม (ระหว่าง 500-3000 ลบ.ม./วิ)
            discharge = random.randint(500, 3000)
            data.append({
                'วันที่': day,
                'เดือน': month,
                'ปี': year,
                'ปริมาณน้ำ (ลบ.ม./วิ)': discharge
            })

# สร้าง DataFrame และบันทึกเป็น Excel
df = pd.DataFrame(data)
df.to_excel('data/dam_discharge_history.xlsx', index=False)
print("สร้างไฟล์ dam_discharge_history.xlsx เรียบร้อยแล้ว")

