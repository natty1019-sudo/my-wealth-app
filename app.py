import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與現金流戰情室", layout="wide", page_icon="🛡️")

# ==========================================
# 0. 快取管理與連線函式 (新功能：加快速度 + 手動更新)
# ==========================================
# 設定 ttl=600 代表資料會暫存 10 分鐘，避免一直狂連 Google 被鎖
# 但透過按鈕可以強制清除快取
@st.cache_data(ttl=600)
def fetch_google_sheet_data():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
        
        client = gspread.authorize(creds)
        # ⚠️ 請確認檔名正確
        sheet_name = "@最新_家用收支入管理表_google程式用" 
        sheet = client.open(sheet_name).sheet1 
        return sheet.get_all_values()
    except Exception as e:
        return str(e) # 回傳錯誤訊息

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
        
        if not item_name or item_name in ["項目", ""]: continue
        if "合計" in item_name: continue
        if "淨值" in item_name: continue
        if "匯率" in item_name: continue

        def clean_num(x):
            if isinstance(x, (int, float)): return x
            x_str = str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()
            return float(x_str) if x_str else 0
        
        val_1 = clean_num(row[1])
        val_3 = clean_num(row[3])

        # 特殊處理：抵利型現金 (備援)
        if "抵利型" in item_name and "房貸" not in item_name and "現金" in item_name:
            amount = max(val_1, val_3)
            assets.append({"類別": "備援現金", "項目": item_name, "金額": amount, "股數": 0, "備援": True})
            continue

        if ("房貸" in item_name or "信貸" in item_name or "借款" in item_name) and "抵利型" not in item_name:
            section = "liability"
        
        if section == "asset":
            amount = val_3 if val_3 > 0 else val_1
            shares = val_1 if val_3 > 0 else 0
            
            category = "其他"
            if "現金" in item_name or "口袋" in item_name or "活存" in item_name or "e財庫" in item_name: category = "現金"
            elif "美股" in item_name or "VT" in item_name or "VOO" in item_name: category = "美股"
            elif "鴻海" in item_name or "0050" in item_name or "台股" in item_name: category = "台股"
            
            assets.append({
                "類別": category, "項目": item_name, "金額": amount, "股數": shares, "備援": False
            })

        elif section == "liability":
            amount = val_1
            if amount > 0:
                liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "股數": 0, "備援": False})

    return pd.DataFrame(assets + liabilities)

# ==========================================
# 2. 主程式邏輯
# ==========================================

# --- 側邊欄：更新按鈕 ---
st.sidebar.header("⚙️ 系統功能")
if st.sidebar.button("🔄 更新最新數據 (Clear Cache)"):
    st.cache_data.clear() # 清除快取
    st.rerun() # 重新執行程式

# --- 讀取資料 ---
raw_data_or_error = fetch_google_sheet_data()

if isinstance(raw_data_or_error, str):
    # 如果回傳的是字串，代表出錯了
    st.error(f"連線錯誤！請檢查 Secrets 或檔名。錯誤訊息: {raw_data_or_error}")
    df = pd.DataFrame()
else:
    # 成功讀取
    df = parse_my_data(raw_data_or_error)

# ==========================================
# 3. 儀表板顯示
# ==========================================
st.title("🛡️ 資產配置與現金流戰情室")

if not df.empty:
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    # 數據計算
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum() 
    
    general_assets_df = assets_df[assets_df['備援'] == False]
    general_assets = general_assets_df['金額'].sum()
    
    normal_cash_df = assets_df[(assets_df['類別'] == '現金') & (assets_df['備援'] == False)]
    normal_cash = normal_cash_df['金額'].sum()
    
    total_assets = general_assets + buffer_cash 
    
    total_liabilities = liabilities_df['金額'].sum()
    net_worth = total_assets + total_liabilities
    
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()

    # 指標區
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("真實總資產", f"${total_assets/10000:,.0f} 萬", help=f"一般: {general_assets/10000:.0f}萬 + 備援: {buffer_cash/10000:.0f}萬")
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    col3.metric("淨資產", f"${net_worth/10000:,.0f} 萬")
    col4.metric("🛡️ 抵利型備援現金", f"${buffer_cash/10000:,.0f} 萬", delta="Layer 4", delta_color="off")
    
    st.info(f"💰 **現金水位**：既有活存 **${normal_cash/10000:,.0f} 萬** (Layer 3) / 抵利型備援 **${buffer_cash/10000:,.0f} 萬** (Layer 4)")

    st.markdown("---")

    # 核心功能區
    st.header("🌊 現金流與提領策略")

    st.sidebar.header("📊 參數設定")
    honhai_eps = st.sidebar.number_input("鴻海預估配息 (元)", value=7.0, step=0.5)
    iwr = st.sidebar.number_input("GK 初始提領率 (%)", value=4.0, step=0.1) / 100
    inflation_rate = st.sidebar.number_input("預估通膨率 (%)", value=2.0, step=0.1) / 100
    monthly_living = st.sidebar.number_input("純生活費 (月)", value=60000, step=5000)
    monthly_debt = st.sidebar.number_input("負債月付金 (房貸/信貸)", value=125000, step=5000)
    
    # 計算邏輯
    annual_living_cost = monthly_living * 12 * (1 + inflation_rate)
    annual_debt_cost = monthly_debt * 12
    total_expense = annual_living_cost + annual_debt_cost

    dividend_income = total_honhai_shares * honhai_eps
    
    gk_base = general_assets 
    gk_total_limit = gk_base * iwr 
    sell_stock_amount = max(0, gk_total_limit - dividend_income) 
    
    funds_stage_1 = dividend_income + sell_stock_amount
    gap_1 = total_expense - funds_stage_1
    
    use_normal_cash = 0
    use_buffer_cash = 0
    
    if gap_1 > 0:
        use_normal_cash = min(gap_1, normal_cash)
        gap_2 = gap_1 - use_normal_cash
        if gap_2 > 0:
            use_buffer_cash = gap_2

    # 版面顯示
    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("📊 收支概況")
        st.write(f"鴻海股數: **{total_honhai_shares:,.0f}** 股")
        st.metric("1. 股息收入", f"${dividend_income:,.0f}", delta="Layer 1")
        st.metric("2. GK 賣股", f"${sell_stock_amount:,.0f}", delta="Layer 2")
        st.metric("3. 總支出需求", f"${total_expense:,.0f}", delta_color="inverse")
        
        st.markdown("---")
        if use_buffer_cash > 0:
            st.error(f"⚠️ **需動用備援金**")
            st.metric("提領金額", f"${use_buffer_cash:,.0f}", delta="Layer 4")
            survival_years = buffer_cash / use_buffer_cash if use_buffer_cash > 0 else 99
            st.write(f"抵利型帳戶可支撐： **{survival_years:.1f} 年**")
        else:
            surplus = (funds_stage_1 + use_normal_cash) - total_expense
            st.success(f"🎉 **現金流充裕**")
            st.metric("年度結餘", f"${surplus:,.0f}")

    with c2:
        st.subheader("🌊 資金瀑布圖")
        
        measure_list = ["relative", "relative"]
        x_list = ["1.股息", "2.賣股(GK)"]
        y_list = [dividend_income, sell_stock_amount]
        text_list = [f"+{dividend_income/10000:.0f}萬", f"+{sell_stock_amount/10000:.0f}萬"]
        
        if use_normal_cash > 0:
            measure_list.append("relative")
            x_list.append("3.既有現金")
            y_list.append(use_normal_cash)
            text_list.append(f"+{use_normal_cash/10000:.0f}萬")
            
        if use_buffer_cash > 0:
            measure_list.append("relative")
            x_list.append("4.備援現金")
            y_list.append(use_buffer_cash)
            text_list.append(f"+{use_buffer_cash/10000:.0f}萬")
            
        measure_list.extend(["total", "relative", "relative", "total"])
        x_list.extend(["可用資金小計", "生活費(含通膨)", "還債", "最終結餘"])
        
        subtotal = dividend_income + sell_stock_amount + use_normal_cash + use_buffer_cash
        
        # 支出轉負數
        y_list.extend([0, -annual_living_cost, -annual_debt_cost, 0])
        
        # 最終結餘 (從 0 開始算，還是從 subtotal 往下扣)
        final_balance = subtotal - annual_living_cost - annual_debt_cost
        
        text_list.extend([
            f"={subtotal/10000:.0f}萬",
            f"-{annual_living_cost/10000:.0f}萬",
            f"-{annual_debt_cost/10000:.0f}萬",
            f"{final_balance/10000:.0f}萬"
        ])
        
        fig = go.Figure(go.Waterfall(
            name = "Cashflow", orientation = "v",
            measure = measure_list,
            x = x_list,
            textposition = "outside",
            text = text_list,
            y = y_list,
            connector = {"line":{"color":"rgb(63, 63, 63)"}},
            decreasing = {"marker":{"color":"#EF553B"}}, 
            increasing = {"marker":{"color":"#00CC96"}}, 
            totals = {"marker":{"color":"#1f77b4"}}
        ))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("資產配置 (含備援)")
        fig_pie = px.pie(assets_df, values='金額', names='類別', hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_chart2:
        st.subheader("資產負債明細表")
        st.dataframe(df, height=300)

else:
    st.info("連線中... 如果很久沒反應，請按左側「更新最新數據」按鈕。")