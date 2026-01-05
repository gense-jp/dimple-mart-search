import streamlit as st
import requests
import pandas as pd
import google.generativeai as genai
from PIL import Image
import io
from datetime import datetime, timedelta, timezone
import time

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
# 0. 為替レート一括取得 (キャッシュ有効)
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
# 1. 画像認識 (自動フォールバック機能付き)
# ==========================================
# キャッシュ有効: 同じ画像ならAPIを消費せず結果を返す
@st.cache_data(show_spinner=False)
def get_product_keyword(image_bytes):
    pil_image = Image.open(io.BytesIO(image_bytes))
    genai.configure(api_key=GEMINI_API_KEY)
    
    # ★ここが重要: 制限の緩い「1.5系」を優先的に試すリスト
    # 2.5系 (latest) は制限がきついのでリストに入れません
    candidate_models = [
        "gemini-1.5-flash",          # 本命 (動けば最強)
        "gemini-1.5-flash-latest",   # 1.5の最新
        "gemini-1.5-flash-001",      # バージョン指定
        "gemini-1.5-flash-002",      # バージョン指定
        "gemini-pro-vision",         # 旧安定版
    ]
    
    last_error = ""
    
    for model_name in candidate_models:
        try:
            # モデルをセット
            model = genai.GenerativeModel(model_name)
            
            prompt = """
            Analyze this image and provide the best "English search keywords" for eBay.
            Format: Brand ModelName ProductName.
            No extra text.
            Example: Sony WH-1000XM5 Black
            """
            
            # 生成実行
            response = model.generate_content([pil_image, prompt])
            
            # ここまで来れば成功！
            return response.text.strip()
            
        except Exception as e:
            # 失敗したら次のモデルを試す
            last_error = str(e)
            continue
    
    # 全部ダメだった場合
    return f"Error: AI解析に失敗しました。({last_error})"

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
    selected_countries = st.multiselect("検索対象の国", list(COUNTRY_CONFIG.keys()), default=default_countries)
    st.divider()
    st.write(f"📊 1 USD = {usd_to_jpy:.2f} JPY")

st.title("🛍️ Dimple Mart Global Pro")
st.write("国別の最安値（送料込み）を比較して、最適な輸出先を見つけます。")

enable_camera = st.checkbox("カメラを起動する")
uploaded_file = None

if enable_camera:
    picture = st.camera_input("商品を撮影")
    if picture: uploaded_file = picture
else:
    uploaded_file = st.file_uploader("写真を選択", type=["jpg", "png", "jpeg"])

if uploaded_file is not None:
    st.image(uploaded_file, caption="解析対象", width=200)
    
    image_bytes = uploaded_file.getvalue()
    
    with st.spinner('🔍 AIが商品を解析中...'):
        keyword = get_product_keyword(image_bytes)
    
    if "Error:" in keyword:
        st.error(keyword)
        st.warning("⚠️ 解決策: Streamlit Cloudの 'Manage app' -> 'Clear cache' を試してみてください。")
    else:
        st.success(f"検索ワード: **{keyword}**")
        
        btn_label = "世界価格をリサーチ (出品中)" if mode_key == "
