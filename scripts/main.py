import sys
import time
import re
from datetime import datetime, timedelta
import pytz
import requests
from bs4 import BeautifulSoup

URL = "https://www.kunsan.ac.kr/dormi/index.kunsan?menuCd=DOM_000000704006003000&&cpath=%2Fdormi"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_soup():
    """기숙사 페이지의 HTML Soup 객체를 안전하게 가져옵니다."""
    try:
        response = requests.get(URL, headers=HEADERS, timeout=10)
        response.encoding = response.apparent_encoding 
        return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"[오류] HTML 요청 중 예외 발생: {e}")
        return None

def parse_meals_by_date(soup, target_date):
    """지정한 날짜의 요일을 찾아 해당 열의 식단을 파싱합니다."""
    if not soup:
        return {}
        
    weekday_str = ["월", "화", "수", "목", "금", "토", "일"][target_date.weekday()]
    
    tables = soup.find_all("table")
    meal_table = None
    
    for t in tables:
        rows = t.find_all("tr")
        is_real_meal_table = False
        for row in rows:
            cells = row.find_all(["td", "th"])
            if cells:
                first_cell_text = cells[0].get_text(strip=True)
                if any(kw in first_cell_text for kw in ["아침", "조식", "점심", "중식", "저녁", "석식"]):
                    is_real_meal_table = True
                    break
        if is_real_meal_table:
            meal_table = t
            break
            
    if not meal_table:
        return {}

    rows = meal_table.find_all("tr")
    col_index = None
    if rows:
        header_cells = rows[0].find_all(["th", "td"])
        for idx, cell in enumerate(header_cells):
            if weekday_str in cell.get_text():
                col_index = idx
                break
    
    if col_index is None:
        col_index = target_date.weekday() + 1
        
    result = {}
    for row in rows:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        
        label = cells[0].get_text(strip=True)
        found_job = None
        
        if "아침" in label or "조식" in label: found_job = "아침"
        elif "점심" in label or "중식" in label: found_job = "점심"
        elif "저녁" in label or "석식" in label: found_job = "저녁"
            
        if found_job and len(cells) > col_index:
            raw = cells[col_index].get_text(separator="\n")
            items = [x.strip() for x in raw.split("\n") if x.strip() and "식단이미지" not in x]
            result[found_job] = items
            
    return result

def wait_until_target(target_hour, target_minute):
    """지정한 목표 시간까지 대기를 유도합니다."""
    kst = pytz.timezone("Asia/Seoul")
    while True:
        now = datetime.now(kst)
        if now.hour == target_hour and now.minute >= target_minute:
            break
        time.sleep(10)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: python main.py [job_type] [webhook_url]")
        sys.exit(1)
        
    job_type = sys.argv[1]
    webhook_url = sys.argv[2]
    
    kst = pytz.timezone("Asia/Seoul")
    today = datetime.now(kst)
    
    soup = get_soup()
    if not soup:
        print("[오류] HTML 데이터를 로드할 수 없어 프로세스를 종료합니다.")
        sys.exit(1)
        
    today_meals = parse_meals_by_date(soup, today)
    
    weekday_ko = ["월", "화", "수", "목", "금", "토", "일"][today.weekday()]
    date_title = f"{today.strftime('%m/%d')} ({weekday_ko})  [점심 - 저녁 - 내일 아침]"
    
    # 1. 종합 식단 전송 로직
    if job_type == "daily":
        lunch_list = today_meals.get("점심", [])
        lunch_text = " · ".join(lunch_list) if lunch_list else "등록된 식단이 없습니다."
        
        dinner_list = today_meals.get("저녁", [])
        dinner_text = " · ".join(dinner_list) if dinner_list else "등록된 식단이 없습니다."
        
        # [조건 분기] 오늘이 일요일(6)인 경우 내일 식단을 긁지 않고 문구로 대체
        if today.weekday() == 6:
            tomorrow_breakfast_text = "새로운 한주를 기대하세요! ✨"
        else:
            tomorrow = today + timedelta(days=1)
            tomorrow_meals = parse_meals_by_date(soup, tomorrow)
            tomorrow_breakfast_list = tomorrow_meals.get("아침", [])
            
            if tomorrow.weekday() >= 5:  # 내일이 주말(토, 일)인 경우
                tomorrow_breakfast_text = "❌ 미운영"
            else:
                tomorrow_breakfast_text = " · ".join(tomorrow_breakfast_list) if tomorrow_breakfast_list else "등록된 식단이 없습니다."
            
        full_content = (
            f"**{date_title}**\n>>> "
            f"🍴**점심**: {lunch_text}\n\n"
            f"🍴**저녁**: {dinner_text}\n\n"
            f"🍴**내일아침**: {tomorrow_breakfast_text}"
        )
        
        payload = {"content": full_content}
        res = requests.post(webhook_url, json=payload)
        print(f"[완료] 전체 식단 전송 완료 (디스코드 상태코드: {res.status_code})")

    # 2. 식사 시작 단일 알림 로직
    elif job_type in ["아침", "점심", "저녁"]:
        is_weekend = today.weekday() >= 5
        if job_type == "아침" and is_weekend: 
            sys.exit(0)
            
        if job_type == "아침": wait_until_target(7, 20)
        elif job_type == "점심": wait_until_target(11, 50) if is_weekend else wait_until_target(11, 20)
        elif job_type == "저녁": wait_until_target(17, 20)
            
        menu_list = today_meals.get(job_type, [])
        content_menu = " · ".join(menu_list) if menu_list else "등록된 메뉴가 없습니다."
        
        payload = {
            "content": f"**{job_type} 메뉴입니다!**\n>>> 🍴 **{job_type}**: {content_menu}"
        }
        res = requests.post(webhook_url, json=payload)
        print(f"[완료] {job_type} 알림 전송 완료 (디스코드 상태코드: {res.status_code})")