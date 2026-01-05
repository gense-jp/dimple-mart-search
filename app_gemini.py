import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
from datetime import datetime, timedelta, timezone

# ==========================================
# 設定エリア
# ==========================================
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    EBAY_APP_ID = st.secrets["EBAY_APP_ID"]
    EBAY_CERT_ID = st.secrets["EBAY_CERT_ID"]
except:
    st.error("APIキー設定エラー: Streamlit CloudのSecretsを確認してください。")
    st.stop()

# 検索対象国の定義
COUNTRY_CONFIG = {
    "🇺🇸 アメリカ": {"id": "EBAY_US", "currency": "USD"},
    "🇬🇧 イギリス": {"id": "EBAY_GB", "currency": "GBP"},
    "🇫🇷 フランス": {"id": "EBAY_FR", "currency": "EUR"},
    "🇩🇪 ドイツ":   {"id": "EBAY_DE", "currency": "EUR"},
    "🇦🇺 オーストラリア": {"id": "EBAY_AU", "currency": "AUD"},
}

# ==========================================
# 0. 為替レート一括取得
# ==========================================
@st.cache_data(ttl=3600)
def get_exchange_rates():
    rates = {"USD": 1.0, "JPY": 150.0, "GBP": 0.79, "EUR": 0.92, "AUD": 1.52, "CAD": 1.35}
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json().get("rates", {})
            for cur in rates.keys():
                if cur in data:
                    rates[cur] = data[cur]
    except:
        pass
    return rates

# ==========================================
# 1. 画像認識 (検索ワード最適化モード)
# ==========================================
@st.cache_data(show_spinner=False)
def get_product_keyword(image_bytes):
    pil_image = Image.open(io.BytesIO(image_bytes))
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 診断で確認済みの上位モデルを使用
    candidate_models = [
        "gemini-2.0-flash",          
        "gemini-2.0-flash-exp",      
        "gemini-flash-latest",       
        "gemini-1.5-pro",            
        "gemini-2.0-flash-lite-preview-02-05"
    ]
    
    last_error = ""
    
    for model_name in candidate_models:
        try:
            model = genai.GenerativeModel(model_name)
            
            # ★ここを修正: 「余計な単語を削れ」という命令を追加
            prompt = """
            Analyze this product image for eBay search.
            
            [CRITICAL INSTRUCTIONS]
            1. Output MUST be in **ENGLISH ONLY**.
            2. **KEEP IT VERY SHORT** (Max 2-4 keywords).
            3. Output ONLY: **Brand + Model Number**.
            4. REMOVE generic words like "Wireless", "Headphones", "Camera", "Lens", "Action Figure" if the Model Number is unique.
            5. REMOVE color names unless it is a special edition.
            6. Do NOT write sentences. Just the keywords.

            Example Bad Output: Sony WH-1000XM5 Wireless Noise Canceling Headphones Black
            Example Good Output: Sony WH-1000XM5
            """
            
            response = model.generate_content([pil_image, prompt])
            
            text = response.text.strip()
            if text:
                return text
            
        except Exception as e:
            last_error = str(e)
            continue
    
    return f"Error: 解析失敗 ({last_error})"

# ==========================================
# 2. eBay検索
# ==========================================
def search_ebay_single(keyword, marketplace_id, limit=3, mode="Active", days_ago=30):
    if not EBAY_APP_ID or not EBAY_CERT_ID:
        return []

    try:
        token_url = "https://api.ebay.com/identity/v1/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"grant_type":
