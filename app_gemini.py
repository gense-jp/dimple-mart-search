import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
from datetime import datetime, timedelta, timezone

# ==========================================
# 設定エリア (クラウド対応版)
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
# 1. 画像認識 (Gemini 2.5 Flash 対応版)
# ==========================================
def get_product_keyword(uploaded_image):
    # 画像データを読み込み
    image_bytes = uploaded_image.getvalue()
    pil_image = Image.open(io.BytesIO(image_bytes))

    # APIキーを設定
    genai.configure(api_key=GEMINI_API_KEY)
    
    # ★診断結果に基づき、確実に存在するモデルを指定
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = """
    Analyze this image and provide the best "English search keywords" for eBay.
    Format: Brand ModelName ProductName.
    No extra text.
    Example: Sony WH-1000XM5 Black
    """
    
    # 生成実行
    response = model.generate_content([pil_image, prompt])
    return response.text.strip()

# ==========================================
# 2. eBay検索
# ==========================================
def search_ebay_single(keyword, marketplace_id, limit=3, mode="Active", days_ago=30):
    if not EBAY_APP_ID or not EBAY_CERT_ID:
        return []

    try:
        token_url = "https://api.ebay.com/identity/v1/oauth2/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
        auth = requests.auth.HTTPBasicAuth(EBAY_APP_ID, EBAY_CERT_ID)
        
        token_res = requests.post(token_url, headers=headers, data=data, auth=auth)
        if token_res.status_code != 200: return []
        token = token_res.json()["access_token"]

        search_url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace_id
        }

        if mode == "Sold":
            past_date = datetime.now(timezone.utc) - timedelta(days=days_ago)
            date_str = past_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            filter_str = f"soldDate:[{date_str}..]"
            sort_order = "-soldDate"
        else:
            filter_str = "buyingOptions:{FIXED_PRICE}"
            sort_order = "price"

        params = {
            "q": keyword,
            "sort": sort_order,
            "limit": limit,
            "filter": filter_str
        }
        
        res = requests.get(search_url, headers=headers, params=params)
        if res.status_code == 200:
            return res.json().get("itemSummaries", [])
        return []
    except:
        return []

# ==========================================
# メイン画面構築
# ==========================================
st.set_page_config(layout="wide", page_title="Dimple Mart Global Pro")

rates = get_exchange_rates()
usd_to_jpy = rates["JPY"]

with st.sidebar:
    st.header("🔍 検索設定")
    search_mode = st.radio("検索モード", ["現在出品中 (Active)", "過去の落札履歴 (Sold)"], index=0)
    mode_key = "Active" if "Active" in search_mode else "Sold"
    
    days_ago = 30
    if mode_key == "Sold":
        period_option = st.selectbox("検索期間", ["過去30日", "過去60日", "過去90日", "過去1年"], index=2)
        if "30" in period_option: days_ago = 30
        elif "60" in period_option: days_ago = 60
        elif "90" in period_option: days_ago = 90
        elif "1" in period_option: days_ago = 365
    
    st.divider()
    default_countries = ["🇺🇸 アメリカ", "🇬🇧 イギリス", "🇫🇷 フランス", "🇩🇪 ドイツ", "🇦🇺 オーストラリア"]
    selected_countries = st.multiselect("検索対象の国", list(COUNTRY_CONFIG.keys()), default=
