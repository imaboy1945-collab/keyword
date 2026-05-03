import os
import time
import hmac
import hashlib
import base64
import requests
import json

CUSTOMER_ID = os.environ.get('CUSTOMER_ID')
ACCESS_LICENSE = os.environ.get('ACCESS_LICENSE')
SECRET_KEY = os.environ.get('SECRET_KEY')

def generate_signature(timestamp, method, uri):
    message = "{}.{}.{}".format(timestamp, method, uri)
    hash = hmac.new(SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(hash.digest()).decode('utf-8')

def get_keyword_data(keywords):
    uri = '/keywordstool'
    method = 'GET'
    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(timestamp, method, uri)
    
    headers = {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Timestamp': timestamp,
        'X-API-KEY': ACCESS_LICENSE,
        'X-Customer': CUSTOMER_ID,
        'X-Signature': signature
    }
    
    params = {'hintKeywords': ','.join(keywords), 'showDetail': '1'}
    res = requests.get('https://api.naver.com' + uri, params=params, headers=headers)
    return res.json()['keywordList']

target_keywords = ['미국주식', '비트코인', '나스닥', '워드프레스']

try:
    data = get_keyword_data(target_keywords)
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("Data updated successfully!")
except Exception as e:
    print(f"Error: {e}")
