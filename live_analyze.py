import sys, json, time, os, base64, hashlib, hmac, re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import requests

CUSTOMER_ID    = os.environ['NAVER_CUSTOMER_ID']
ACCESS_LICENSE = os.environ['NAVER_ACCESS_LICENSE']
SECRET_KEY     = os.environ['NAVER_SECRET_KEY']
CLIENT_ID      = os.environ['NAVER_CLIENT_ID']
CLIENT_SECRET  = os.environ['NAVER_CLIENT_SECRET']
KST = timezone(timedelta(hours=9))


def generate_signature(timestamp, method, uri):
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(SECRET_KEY.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def parse_count(value):
    if value in (None, '', '-'): return 0
    if isinstance(value, int): return value
    text = str(value).strip().replace(',', '')
    if text == '< 10': return 10
    m = re.search(r'\d+', text)
    return int(m.group(0)) if m else 0


def get_keyword_stats(keyword):
    uri = '/keywordstool'
    timestamp = str(int(time.time() * 1000))
    headers = {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Timestamp': timestamp,
        'X-API-KEY': ACCESS_LICENSE,
        'X-Customer': CUSTOMER_ID,
        'X-Signature': generate_signature(timestamp, 'GET', uri),
    }
    r = requests.get('https://api.naver.com' + uri,
                     params={'hintKeywords': keyword, 'showDetail': '1'},
                     headers=headers, timeout=20)
    r.raise_for_status()
    items = r.json().get('keywordList', [])
    for item in items:
        if item.get('relKeyword', '').strip() == keyword.strip():
            return item
    return items[0] if items else None


def get_search_total(keyword, target):
    url = (f"https://openapi.naver.com/v1/search/{target}.json"
           f"?query={quote(keyword)}&display=1")
    r = requests.get(url, headers={
        'X-Naver-Client-Id': CLIENT_ID,
        'X-Naver-Client-Secret': CLIENT_SECRET,
    }, timeout=20)
    return int(r.json().get('total', 0)) if r.ok else 0


def calculate_grade(ratio, daily_avg, mobile_share):
    if ratio < 0.5 and daily_avg >= 20 and mobile_share >= 0.45: return 'S'
    if ratio < 1.5 and daily_avg >= 10: return 'A'
    if ratio < 4.0: return 'B'
    if ratio < 8.0: return 'C'
    return 'D'


def opportunity_score(monthly_total, blog_total, cafe_total, news_total):
    demand = monthly_total / 30
    competition = max(blog_total + cafe_total * 0.35 + news_total * 0.2, 1)
    return round((demand * 1000) / competition, 3)


def main():
    keyword = ' '.join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ''
    if not keyword:
        print("키워드를 입력해주세요", file=sys.stderr)
        sys.exit(1)

    print(f"[분석 시작] '{keyword}'")

    stats = get_keyword_stats(keyword)
    if stats:
        pc     = parse_count(stats.get('monthlyPcQcCnt'))
        mobile = parse_count(stats.get('monthlyMobileQcCnt'))
    else:
        pc = mobile = 0

    monthly_total = pc + mobile
    daily_avg     = round(monthly_total / 30, 2)
    time.sleep(0.15)

    blog_total = get_search_total(keyword, 'blog');       time.sleep(0.15)
    cafe_total = get_search_total(keyword, 'cafearticle'); time.sleep(0.15)
    news_total = get_search_total(keyword, 'news')

    mobile_share = round(mobile / monthly_total, 3) if monthly_total > 0 else 0
    ratio        = round(blog_total / monthly_total, 2) if monthly_total > 0 else 0
    score        = opportunity_score(monthly_total, blog_total, cafe_total, news_total)
    grade        = calculate_grade(ratio, daily_avg, mobile_share)

    result = {
        'keyword':           keyword,
        'pc_search':         pc,
        'mobile_search':     mobile,
        'monthly_total':     monthly_total,
        'daily_avg':         daily_avg,
        'mobile_share':      mobile_share,
        'grade':             grade,
        'opportunity_score': score,
        'ratio':             ratio,
        'blog_total':        blog_total,
        'cafe_total':        cafe_total,
        'news_total':        news_total,
        'analyzed_at':       datetime.now(KST).isoformat(timespec='seconds'),
        'status':            'done',
    }

    with open('live_result.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[완료] {grade}등급 | 황금도 {score} | 월검색 {monthly_total:,}")


if __name__ == '__main__':
    main()
