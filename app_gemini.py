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
# 1. 画像認識 (英語強制モード)
# ==========================================
@st.cache_data(show_spinner=False)
def get_product_keyword(image_bytes):
    pil_image = Image.open(io.BytesIO(image_bytes))
    genai.configure(api_key=GEMINI_API_KEY)
    
    # 賢い順にモデルを指名
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
            
            # ★ここを修正: 日本語を徹底的に禁止し、英語のみを強制する命令
            prompt = """
            Analyze this product image for eBay listing.
            
            [CRITICAL INSTRUCTIONS]
            1. Output MUST be in **ENGLISH ONLY**.
            2. Do NOT use Japanese or any other language.
            3. Identify Brand, Model Number (very important), and Product Name.
            4. Output ONLY the keywords string.
            
            Example Input: (Image of a Sony camera)
            Example Output: Sony Alpha a7 IV Mirrorless Camera Body
            """
            
            response = model.generate_content([pil_image, prompt])
            
            # 念のため、結果が空でなければ返す
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
        st.error(f"AI解析エラー: {keyword}")
    else:
        # 結果を表示（万が一日本語が混ざっていても編集可能にしておく）
        st.success("✅ AI解析完了")
        keyword = st.text_input("検索ワード (必要に応じて修正)", value=keyword)
        
        btn_label = "世界価格をリサーチ (出品中)" if mode_key == "Active" else f"販売実績を確認 (過去{days_ago}日)"
        
        if st.button(btn_label, type="primary"):
            all_data = []
            progress_bar = st.progress(0)
            
            for i, country_name in enumerate(selected_countries):
                config = COUNTRY_CONFIG[country_name]
                items = search_ebay_single(keyword, config["id"], limit=5, mode=mode_key, days_ago=days_ago)
                
                if not items and mode_key == "Sold":
                    all_data.append({
                        "国": country_name,
                        "商品タイトル": "⚠️ 販売実績なし",
                        "トータル(円)": "-",
                        "詳細(現地通貨)": "-",
                        "リンク": "#",
                        "sort_price": 99999999
                    })
                    continue

                for item in items:
                    title = item.get("title", "No Title")
                    url = item.get("itemWebUrl", item.get("url"))
                    
                    price_info = item.get("price", {})
                    item_price = float(price_info.get("value", 0))
                    currency = price_info.get("currency", "USD")
                    
                    shipping_cost = 0.0
                    shipping_opts = item.get("shippingOptions", [])
                    if shipping_opts:
                        first_opt = shipping_opts[0]
                        ship_cost_info = first_opt.get("shippingCost", {})
                        shipping_cost = float(ship_cost_info.get("value", 0))
                    
                    total_local = item_price + shipping_cost
                    rate_to_usd = rates.get(currency, 1.0)
                    if currency == "USD":
                        total_usd = total_local
                    else:
                        total_usd = total_local / rate_to_usd if rate_to_usd else 0
                    
                    total_jpy = total_usd * usd_to_jpy
                    
                    detail_text = f"{item_price:.2f} + 送{shipping_cost:.2f} {currency}"
                    
                    date_display = ""
                    if mode_key == "Sold":
                        sold_date_raw = item.get("soldDate") or item.get("itemEndDate", "")
                        if sold_date_raw:
                            date_display = sold_date_raw[:10]
                        else:
                            date_display = "-"

                    data_row = {
                        "国": country_name,
                        "商品タイトル": title,
                        "トータル(円)": f"¥{int(total_jpy):,}",
                        "詳細(現地通貨)": detail_text,
                        "リンク": url,
                        "sort_price": total_jpy
                    }
                    if mode_key == "Sold":
                        data_row["販売日"] = date_display
                        
                    all_data.append(data_row)
                
                progress_bar.progress((i + 1) / len(selected_countries))
            
            progress_bar.empty()
            
            if all_data:
                df = pd.DataFrame(all_data)
                
                if mode_key == "Active":
                    valid_rows = df[df["トータル(円)"] != "-"]
                    if not valid_rows.empty:
                        st.divider()
                        st.subheader("🌎 国別・最安値一覧 (送料込み)")
                        st.caption("各国の市場価格（ライバルの最安値）です。")
                        dashboard_cols = st.columns(len(selected_countries))
                        for i, country in enumerate(selected_countries):
                            country_df = valid_rows[valid_rows["国"] == country]
                            with dashboard_cols[i]:
                                if not country_df.empty:
                                    best_idx = country_df["sort_price"].idxmin()
                                    best_price = country_df.loc[best_idx, "トータル(円)"]
                                    st.metric(label=country, value=best_price)
                                else:
                                    st.metric(label=country, value="なし")
                        st.divider()

                st.write("### 詳細データ一覧")
                cols = ["国", "トータル(円)", "詳細(現地通貨)", "商品タイトル", "リンク"]
                if mode_key == "Sold":
                    cols.insert(1, "販売日")
                
                st.data_editor(
                    df[cols],
                    column_config={
                        "リンク": st.column_config.LinkColumn("商品ページ"),
                        "詳細(現地通貨)": st.column_config.TextColumn("内訳 (本体+送料)"),
                        "トータル(円)": st.column_config.TextColumn("合計 (円換算)"),
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                if mode_key == "Sold":
                    sold_count = len(df[df["トータル(円)"] != "-"])
                    if sold_count > 0:
                        st.success(f"✅ 過去{days_ago}日間で {sold_count}件 の販売実績あり")
                    else:
                        st.error("❌ 販売実績なし")
            else:
                st.warning("データが見つかりませんでした。")
