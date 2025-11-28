import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與現金流戰情室", layout="wide", page_icon="🛡️")

# ==========================================
# 1. 資料處理核心
# ==========================================
def parse_my_data(raw_data):
    assets = []
    liabilities = []
    section = "asset"
    
    for row in raw_data:
        row = row + [''] * (5 - len(row))
        item_name = str(row[0]).strip()
        
        if "資產合計" in item_name or "美金匯率" in item_name:
            section = "switch_to_liability_soon"
            continue
        
        if section == "switch_to_liability_soon" and ("房貸" in item_name or "信貸" in item_name or "借款" in item_name):
            section = "liability"

        if not item_name or item_name in ["項目", ""]: continue
        if "合計" in item_name or "淨值" in item_name: continue

        def clean_num(x):
            if isinstance(x, (int, float)): return x
            x_str = str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()
            return float(x_str) if x_str else 0

        try:
            if section == "asset":
                amount = clean_num(row[3])
                shares = clean_num(row[1]) if row[1] else 0
                
                if amount == 0 and shares > 10000 and "現金" in item_name: 
                    amount = shares
                    shares = 0
                
                category = "其他"
                if "現金" in item_name or "口袋" in item_name or "活存" in item_name: category = "現金"
                elif "美股" in item_name or "VT" in item_name or "VOO" in item_name or "TSLA" in item_name: category = "美股"
                elif "鴻海" in item_name or "0050" in item_name or "台股" in item_name: category = "台股"
                
                is_buffer = "抵利型" in item_name

                assets.append({
                    "類別": category, "項目": item_name, "金額": amount, "股數": shares, "備援": is_buffer
                })

            elif section == "liability":
                amount = clean_num(row[1])
                if amount > 0:
                    liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "股數": 0, "備援": False})

        except ValueError:
            continue

    return pd.DataFrame(assets + liabilities)

# ==========================================
# 2. 資料來源設定 (正式連線模式)
# ==========================================
try:
    # 設定連線範圍
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 讀取 Secrets (Streamlit 雲端) 或本地金鑰
    if "gcp_service_account" in st.secrets:
[gcp_service_account]
type = "service_account"
project_id = "my-project-new-life-479502"
private_key_id = "85e67562676648907c7b610ecd9f39a0d37ea539"
private_key = "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCcjv8raQJceRzw\nLozCTEGKrQzAaKTFPawyzfNizedrylrqSbaP0tjHVEzH0U3gGH2mJ6piuluYnVAu\nTEkWLVcDSpWQEv5RX0Oh9eBYtde0nUk8yNMsgZKEjtiJJx3VhX4+8d0l3I89oICg\n3lsSEm5IeIHrJ2yyi4ASPKMnrnqfrsNnqVNPXDU1QiRt/5UDYUB4iYsolNrkuGiN\niDFT0bmKzndKIpuZwbfTKlm3HkihtZvu1yZbbrAp2vqPmiMJWJo+9ANmGabYcdfN\nWbAxSjhVF0eMWGUeZGUVKl6OSVAxTwYhwLTY1fGlk1Qc0MDJXuBRUm8/5HYFQAC+\n1k2jutEVAgMBAAECggEADcoonp26uANw8ZTgEBMgaMMSTvZIoRjsDHOIfwjs29kw\nhddlTajAMFp0AtukNNtjYdm3j8ejXr9oexN8Eoh+1ArjPpP1s5wk/GSIVLf7nmyG\nMWTs+MwW6DceyoHYBmEiPBAYrweM1FxJSCIdumtGLHr00o4f7GAOMU0G/+1F3r+m\nL9zsIGKw/rg383LTVn3t/ngVl/LZVe/+dRe5qIiQRl7A9VKJciZr9CCRxK1aoW2W\nIOErVzNKBkdzPtYJQAZf0b9I08jCOHx2Dv6TyJkjATg43qjqJ/vNyeTuayRd009j\ncsFryjLRhmO0oldQfMChVvJViSmam8vpia5F/GvTBwKBgQDLf1bMs6zoWjj3w+UM\nHSSridI74l3Gi1biVyrhuJN8xE5Zm1vCV43baaRBVvHc1AeZ/4tUnSRTE/3sXyHu\nQq/N61eHhzPgN6R9e0dGOCirgxp1nNfaHu5AfZxWVvfZffgNhlpzxirVUCeYNt2I\nPEgc3HmJXUEJ+QCqLuQOln17bwKBgQDE820+/ouEOnEHyBIeOlTGOuFwC8+lmVav\nkC8FwVQQsjtn8L6y6UpRmaP9lBPiBfKtoVz46JfJHVZYv4Y9EQDsyLryodOGwYA6\ns8mD7mb+qyDkszhlhzaOxmYghAF7rpAUhJDe7M/57rM+kXJloMvmT4rvQ92YSiJo\nhOl1PJFJuwKBgQCVWRV5EnzZ4i1hGXImm9Tn2DRlItMz/dt8LgEYu//yV5gxB2Ym\nkV9ZIoUcNxU2vp39laDKLrIUDt4S9hbO6D5iYFBS9RVLf0rHlQxQKrMefQ+UNdHt\nETpGNmngq98mzd6Y/nuv8EZLW5JTkiCv9Z3vIJhKChjLmuW0AMn7MtNRHQKBgQDE\nUFRLn1QX6Fz0QbP1l3Ua5mQB2HQQ/8hNVS3Z0bvmrJHUaD7dfPaMYdX5lBlBiWY9\nNgPDQ6zQVcLU0YuP4RwH6YmXAkEjKEuVt9GdBQx6ur8d15rWcLGsHQx9Srdjvjt1\niDITUv93hDv8mOPrcxzrI8w79Gy0OOkVP66pIkc7swKBgHRyLuSpTwiy+jZo/Vog\nO/XkXB4d2wXvC2SI97JSkEb8sCk0S4in/RdYY9dqZaxq186etzNgjPyQ4R1MEDbF\nnXGFN0feJJ/isj3a716sG5q+Z/PPEOhfUFT0yowb7FdCVN9rY65xfq2HWbXzMXWX\ne7cGmbFMB4tv/2ty5/4PKOV+\n-----END PRIVATE KEY-----\n"
"client_email = "finance-app@my-project-new-life-479502.iam.gserviceaccount.com"
"client_id = "110145608507445000054"
"auth_uri = "https://accounts.google.com/o/oauth2/auth"
"token_uri = "https://oauth2.googleapis.com/token"
"auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
"client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/finance-app%40my-project-new-life-479502.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
    
    # -----------------------------------------------------------------
    # ⚠️【請修改這裡】⚠️
    # 請將下方引號內的文字，改成您 Google 試算表左上角的標題名稱
    # -----------------------------------------------------------------
    sheet_name = "@最新_家用收支入管理表_google程式用"  # <--- 修改這裡 (例如改成 "我的資產表")
    
    # 讀取第一個分頁 (假設您的資料在第一頁)
    sheet = client.open(sheet_name).sheet1 
    raw_data_paste = sheet.get_all_values()
    
    # 解析資料
    df = parse_my_data(raw_data_paste)

except Exception as e:
    st.error(f"連線失敗！請檢查：1. 試算表名稱是否正確？ 2. 是否已共用給機器人 Email？ 錯誤訊息: {e}")
    df = pd.DataFrame() # 建立空資料表避免當機

# ==========================================
# 3. 儀表板顯示邏輯
# ==========================================
st.title("🛡️ 資產配置與現金流戰情室")

if not df.empty:
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    total_assets = assets_df['金額'].sum()
    total_liabilities = liabilities_df['金額'].sum()
    net_worth = total_assets + total_liabilities
    
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum()
    
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()

    # 指標列
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("淨資產", f"${net_worth/10000:,.0f} 萬")
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    col3.metric("🛡️ 抵利型備援現金", f"${buffer_cash/10000:,.0f} 萬")
    
    lv_ratio = abs(total_liabilities) / total_assets if total_assets > 0 else 0
    col4.metric("槓桿比率", f"{lv_ratio:.1%}", delta="偏高" if lv_ratio > 0.5 else "安全", delta_color="inverse")

    st.markdown("---")

    # 現金流與提領
    st.header("🌊 年度現金流試算 (股息 + 提領)")
    
    st.sidebar.header("現金流參數")
    honhai_dps = st.sidebar.slider("預估鴻海股利 (元/股)", 0.0, 10.0, 5.5, 0.5)
    monthly_expense = st.sidebar.number_input("預估每月生活費 (元)", value=100000, step=5000)
    annual_expense = monthly_expense * 12
    
    estimated_dividend = total_honhai_shares * honhai_dps
    
    c1, c2 = st.columns([1, 2])
    
    with c1:
        st.subheader("收入來源預估")
        st.write(f"持有鴻海股數: **{total_honhai_shares:,.0f}** 股")
        st.metric("預估年度股息", f"${estimated_dividend:,.0f}")
        
        survival_months = buffer_cash / monthly_expense if monthly_expense > 0 else 0
        st.info(f"🛡️ **安全氣囊**：抵利型現金可支撐 **{survival_months:.1f} 個月** 生活費。")

    with c2:
        st.subheader("GK 提領與現金流瀑布圖")
        
        iwr = st.sidebar.number_input("初始提領率 (%)", 3.0, 6.0, 4.0, 0.1) / 100
        
        # 淨投資部位 (扣除負債後的淨值 - 備援現金)
        net_investable = net_worth - buffer_cash
        target_withdraw = net_investable * iwr
        gap = target_withdraw - estimated_dividend
        
        fig_waterfall = go.Figure(go.Waterfall(
            name = "Cashflow", orientation = "v",
            measure = ["relative", "relative", "total", "total"],
            x = ["預估股息", "需賣資產", "可提領總額", "生活費需求"],
            textposition = "outside",
            text = [f"{estimated_dividend/10000:.1f}萬", f"{gap/10000:.1f}萬", f"{target_withdraw/10000:.1f}萬", f"{annual_expense/10000:.1f}萬"],
            y = [estimated_dividend, gap, target_withdraw, annual_expense],
            connector = {"line":{"color":"rgb(63, 63, 63)"}},
            decreasing = {"marker":{"color":"#EF553B"}},
            increasing = {"marker":{"color":"#00CC96"}},
            totals = {"marker":{"color":"#636EFA"}}
        ))
        fig_waterfall.update_layout(title="資金來源 vs 生活支出", showlegend=False, height=400)
        st.plotly_chart(fig_waterfall, use_container_width=True)
        
        if target_withdraw > annual_expense:
            st.success(f"🎉 資金充裕 (盈餘 ${target_withdraw - annual_expense:,.0f})")
        else:
            st.warning(f"⚠️ 提領上限 (${target_withdraw:,.0f}) 低於生活費需求")

    st.markdown("---")
    with st.expander("查看原始數據"):
        st.dataframe(df)

else:
    st.info("正在建立連線...")