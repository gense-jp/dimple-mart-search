import streamlit as st
import google.generativeai as genai

st.title("🔧 Gemini API 接続診断ツール")

# 1. APIキーの読み込み確認
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    # セキュリティのため、先頭4文字と末尾4文字だけ表示
    masked_key = f"{api_key[:4]}...{api_key[-4:]}"
    st.write(f"✅ APIキーを読み込みました: **{masked_key}**")
    
    # ここでキーの中身をチェック
    if '"' in api_key or ' ' in api_key:
        st.error("⚠️ 警告: APIキーの中に「引用符」や「スペース」が含まれています！Secretsの設定を見直してください。")
    
    # 設定
    genai.configure(api_key=api_key)

except Exception as e:
    st.error(f"❌ APIキーの読み込みに失敗しました: {e}")
    st.stop()

# 2. 利用可能なモデル一覧を取得
st.write("---")
st.write("📡 Googleサーバーと通信中...")

try:
    models = genai.list_models()
    st.write("### 利用可能なモデル一覧")
    
    found_flash = False
    for m in models:
        # "generateContent" ができるモデルだけ表示
        if 'generateContent' in m.supported_generation_methods:
            st.code(m.name) # モデル名を表示
            if "flash" in m.name:
                found_flash = True

    if found_flash:
        st.success("✅ 'flash' モデルが見つかりました！通信は成功しています。")
    else:
        st.warning("⚠️ 通信はできましたが、Flashモデルが見当たりません。")

except Exception as e:
    st.error(f"❌ 通信エラー: {e}")
    st.write("考えられる原因: APIキーが無効、またはGoogle Cloud側でAPIが有効になっていません。")
