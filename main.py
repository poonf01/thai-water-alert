import pandas as pd
from datetime import datetime
import locale

# ตั้งค่า locale สำหรับการแปลงชื่อเดือนภาษาไทย
locale.setlocale(locale.LC_ALL, 'th_TH.UTF-8')

def thai_month_to_int(month_thai):
    """Converts Thai month name to its corresponding integer (1-12)."""
    month_map = {
        'มกราคม': 1, 'กุมภาพันธ์': 2, 'มีนาคม': 3, 'เมษายน': 4,
        'พฤษภาคม': 5, 'มิถุนายน': 6, 'กรกฎาคม': 7, 'สิงหาคม': 8,
        'กันยายน': 9, 'ตุลาคม': 10, 'พฤศจิกายน': 11, 'ธันวาคม': 12
    }
    return month_map.get(month_thai, None)

def load_and_preprocess_data(file_path):
    """
    Loads CSV data, preprocesses it by converting Thai month to int,
    combining date columns, and setting 'date' as index.
    """
    df = pd.read_csv(file_path)

    # Rename columns for easier access
    df.columns = ['day', 'month_thai', 'year', 'discharge_m3_per_s']

    # Convert Thai month to integer
    df['month'] = df['month_thai'].apply(thai_month_to_int)

    # Convert Buddhist year (BE) to Common Era (CE) if necessary
    # Assuming years like 2567 are BE and need to be converted to 2024
    # Check if the year is in BE format (e.g., > 2400) and convert
    df['year'] = df['year'].apply(lambda x: x - 543 if x > 2400 else x)


    # Create a datetime column
    # Use errors='coerce' to turn invalid date parsing into NaT (Not a Time)
    df['date'] = pd.to_datetime(df[['year', 'month', 'day']], errors='coerce')

    # Drop rows where date could not be parsed
    df.dropna(subset=['date'], inplace=True)

    # Set 'date' as index for easier time-series operations
    df.set_index('date', inplace=True)

    # Select and return relevant columns
    return df[['discharge_m3_per_s']]

# --- Main script execution ---
if __name__ == "__main__":
    # File paths (update if your files are in a different location)
    file_2554 = 'ระดับน้ำปี2554.xlsx - ทำข้อมูลเป็นคอลัมแยกข้อมูล น้ำแ.csv'
    file_2567 = 'ระดับน้ำปี2567.xlsx - โหลดไม่ได้ส่งเป็นชีดมาใหม่.csv'
    file_complete = 'dam_discharge_history_complete.csv'

    # Load and preprocess data from all files
    df_2554 = load_and_preprocess_data(file_2554)
    df_2567 = load_and_preprocess_data(file_2567)
    df_complete = load_and_preprocess_data(file_complete)

    # Combine all data (handle potential overlaps by taking the latest/most complete)
    # For simplicity, we'll just concatenate and drop duplicates for the same date
    # In a real scenario, you might want a more sophisticated merge/update strategy
    all_data = pd.concat([df_2554, df_2567, df_complete]).sort_index()
    all_data = all_data[~all_data.index.duplicated(keep='last')] # Keep the last occurrence for duplicate dates

    # Get today's date (or the latest date in your data if simulating)
    # For actual today's date:
    # today = datetime.now()
    # For demonstration, let's use the last date available in our combined data as 'latest_date'
    # This simulates getting the most recent data point.
    latest_date_in_data = all_data.index.max()
    print(f"ข้อมูลล่าสุดในชุดข้อมูลคือ: {latest_date_in_data.strftime('%d %B %Y')}")

    # Extract year for easy filtering
    all_data['year_ce'] = all_data.index.year

    # Filter data for year 2011 (2554 BE) and 2024 (2567 BE)
    data_2011 = all_data[all_data['year_ce'] == 2011]
    data_2024 = all_data[all_data['year_ce'] == 2024]

    # --- Prepare for comparison ---
    # Create a common index for comparison based on month-day
    data_2011['month_day'] = data_2011.index.strftime('%m-%d')
    data_2024['month_day'] = data_2024.index.strftime('%m-%d')

    # Merge dataframes on month-day for easy comparison
    comparison_df = pd.merge(
        data_2024.rename(columns={'discharge_m3_per_s': 'Discharge_2024'}),
        data_2011.rename(columns={'discharge_m3_per_s': 'Discharge_2011'}),
        on='month_day',
        how='outer' # Use outer to include all dates present in either year
    )

    # Clean up and add original date columns for clarity
    comparison_df['Date_2024'] = pd.to_datetime(comparison_df['month_day'] + '-' + comparison_df['year_ce_x'].astype(str))
    comparison_df['Date_2011'] = pd.to_datetime(comparison_df['month_day'] + '-' + comparison_df['year_ce_y'].astype(str))

    # Select relevant columns for display
    comparison_df = comparison_df[['month_day', 'Date_2024', 'Discharge_2024', 'Date_2011', 'Discharge_2011']]
    comparison_df.set_index('month_day', inplace=True)
    comparison_df.sort_index(inplace=True)


    print("\n--- การเปรียบเทียบปริมาณการปล่อยน้ำท้ายเขื่อนเจ้าพระยา (ลบ.ม./วินาที) ---")
    print(comparison_df.to_string()) # .to_string() to show all rows if dataframe is large

    print("\n--- การแจ้งเตือนและข้อมูลวันล่าสุด ---")

    # Get data for the latest_date (today or last available in data)
    latest_discharge_2024 = data_2024.loc[data_2024.index == latest_date_in_data, 'discharge_m3_per_s'].values
    # Get the corresponding month-day for latest_date
    latest_date_month_day = latest_date_in_data.strftime('%m-%d')
    # Find discharge for 2011 on the same month-day
    latest_discharge_2011 = data_2011.loc[data_2011['month_day'] == latest_date_month_day, 'discharge_m3_per_s'].values


    print(f"วันที่ล่าสุดในข้อมูล: {latest_date_in_data.strftime('%d %B %Y')}")

    if latest_discharge_2024.size > 0:
        print(f"ปริมาณน้ำปี 2567 (2024) วันที่ {latest_date_in_data.strftime('%d %B')}: {latest_discharge_2024[0]:.0f} ลบ.ม./วินาที")
    else:
        print(f"ไม่มีข้อมูลปริมาณน้ำสำหรับปี 2567 (2024) ในวันที่ {latest_date_in_data.strftime('%d %B')}")

    if latest_discharge_2011.size > 0:
        print(f"ปริมาณน้ำปี 2554 (2011) วันที่ {latest_date_in_data.strftime('%d %B')}: {latest_discharge_2011[0]:.0f} ลบ.ม./วินาที")
    else:
        print(f"ไม่มีข้อมูลปริมาณน้ำสำหรับปี 2554 (2011) ในวันที่ {latest_date_in_data.strftime('%d %B')}")

    # Optional: Add simple alert logic
    if latest_discharge_2024.size > 0 and latest_discharge_2011.size > 0:
        diff = latest_discharge_2024[0] - latest_discharge_2011[0]
        if diff > 0:
            print(f"**แจ้งเตือน:** ปริมาณน้ำปี 2567 วันนี้สูงกว่าปี 2554 ในวันเดียวกัน: {abs(diff):.0f} ลบ.ม./วินาที")
        elif diff < 0:
            print(f"**แจ้งเตือน:** ปริมาณน้ำปี 2567 วันนี้ต่ำกว่าปี 2554 ในวันเดียวกัน: {abs(diff):.0f} ลบ.ม./วินาที")
        else:
            print(f"ปริมาณน้ำปี 2567 และปี 2554 วันนี้เท่ากัน")
