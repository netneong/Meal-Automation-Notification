import sys
import time
import re
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup

URL = "https://www.kunsan.ac.kr/dormi/index.kunsan?menuCd=DOM_000000704006003000&&cpath=%2Fdormi"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_today_meals():
    """HTML 테이블을 구조적으로 검사하여 진짜 식단 표를 찾아 파싱합니다."""
    kst = pytz.timezone("Asia/Seoul")
    today = datetime.now(kst)
    col_index = today.weekday() + 1 
    
    try:
        response = requests.get(URL, headers=HEADERS, timeout=10)
        response.encoding = response.apparent_encoding 
        soup = BeautifulSoup(response.text, "html.parser")
        
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
            print("[오류] 실제 식단 구조를 가진 테이블을 찾지 못했습니다.")
            return None, today

        rows = meal_table.find_all("tr")
        result = {}
        
        for row in rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            
            label = cells[0].get_text(strip=True)
            found_job = None
            
            if "아침" in label or "조식" in label:
                found_job = "아침"
            elif "점심" in label or "중식" in label:
                found_job = "점심"
            elif "저녁" in label or "석식" in label:
                found_job = "저녁"
                
            if found_job and len(cells) > col_index:
                raw = cells[col_index].get_text(separator="\n")
                items = [x.strip() for x in raw.split("\n") if x.strip() and "식단이미지" not in x]
                result[found_job] = items
                
        return result, today
    except Exception as e:
        print(f"[오류] 스크래핑 수행 중 예외 발생: {e}")
        return None, today

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
    
    meals, today_date = get_today_meals()
    
    if not meals or not any(meals.values()):
        print("[오류] 최종 식단 데이터가 비어있습니다. 파싱할 수 없습니다.")
        sys.exit(1)
        
    is_weekend = today_date.weekday() >= 5
    date_str = today_date.strftime("%Y-%m-%d")
    
    if job_type == "daily":
        payload = {
            "content": "", 
            "embeds": [{
                "title": f"📅 {date_str} 오늘의 기숙사 식단 전체보기",
                "color": 3447003,
                "fields": []
            }]
        }
        for name in ["아침", "점심", "저녁"]:
            menu_list = meals.get(name, [])
            menu_text = ", ".join(menu_list) if menu_list else "등록된 식단이 없습니다."
            if name == "아침" and is_weekend:
                menu_text = "❌ 주말 아침은 운영하지 않습니다."
            payload["embeds"][0]["fields"].append({"name": f"🍴 {name}", "value": menu_text, "inline": False})
            
        res = requests.post(webhook_url, json=payload)
        print(f"[완료] 전체 식단 전송 완료 (디스코드 상태코드: {res.status_code})")

    elif job_type in ["아침", "점심", "저녁"]:
        if job_type == "아침" and is_weekend: 
            sys.exit(0)
            
        if job_type == "아침": wait_until_target(7, 30)
        elif job_type == "점심": wait_until_target(11, 50) if is_weekend else wait_until_target(11, 30)
        elif job_type == "저녁": wait_until_target(17, 30)
            
        menu_list = meals.get(job_type, [])
        menu_text = "\n".join([f"- {item}" for item in menu_list]) if menu_list else "등록된 메뉴가 없습니다."
        
        payload = {
            "content": f"🔔 **@here {job_type} 식사 시작 10분 전입니다!**", 
            "embeds": [{
                "title": f"🍱 오늘의 {job_type} 메뉴",
                "description": menu_text,
                "color": 15105570
            }]
        }
        res = requests.post(webhook_url, json=payload)
        print(f"[완료] {job_type} 알림 전송 완료 (디스코드 상태코드: {res.status_code})")