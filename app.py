import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與現金流戰情室", layout="wide", page_icon="🛡️")

# ==========================================
# 1. 資料處理核心 (邏輯不變：確保讀取所有現金行)
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

        # --- 特殊處理：抵利型現金 (備援) ---
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
# 2. 資料來源設定
# ==========================================

# --- 模式 A: 測試數據 (已修正：補齊您的 400多萬現金 + 652萬備援) ---
raw_data_paste = [
    ["鴻海股票（質押中）", "142000", "229.5", "32,589,000"],
    ["鴻海股票（可動用）", "80000", "229.5", "18,360,000"],
    ["0050 ETF", "20,000", "61.95", "1,239,000"],
    ["美股資產", "", "", "4,000,000"],
    
    # 這裡補上您之前提到的多筆現金，加起來約 420 萬
    ["現金_e財庫", "", "", "274,086"],
    ["現金_凱基銀行", "", "", "3,083,694"],
    ["現金_國泰", "", "", "217,433"],
    ["現金_LINK Bank口袋帳戶", "", "", "500,000"],
    ["現金_富邦_活期", "", "", "119,684"],
    
    ["✅ 資產合計", "", "", "xxxx"], 
    ["", "", "", ""],
    ["富邦房貸", "11,540,000", "2.60%", ""],
    ["股票質押借款", "16,020,000", "2.41%", ""],
    ["其他信貸", "6,960,000", "", ""], 
    ["❌ 負債合計", "34,520,000", "", ""], 
    ["", "", "", ""],
    
    # 這是最底下的備援金 652萬
    ["現金_富邦_抵利型現金帳戶", "", "", "6,520,000"]
]

# --- 模式 B: 正式連線 Google Sheets ---
# ⚠️ 確認數字無誤後，請刪除上面的 raw_data_paste，並解開下面註解
# -------------------------------------------------------
# try:
#     scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
#     if "gcp_service_account" in st.secrets:
#         creds_dict = st.secrets["gcp_service_account"]
#         creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
#     else:
#         creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
#     client = gspread.authorize(creds)
#     sheet = client.open("2024資產負債表").sheet1 
#     raw_data_paste = sheet.get_all_values()
# except Exception as e:
#     st.error(f"連線失敗: {e}")
#     raw_data_paste = []
# -------------------------------------------------------

df = parse_my_data(raw_data_paste)

# ==========================================
# 3. 儀表板顯示邏輯
# ==========================================
st.title("🛡️ 資產配置與現金流戰情室")

if not df.empty:
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    # --- 關鍵數據計算 ---
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum() # 約 652 萬
    
    general_assets_df = assets_df[assets_df['備援'] == False]
    general_assets = general_assets_df['金額'].sum() # 股票 + 一般現金 (~400多萬)
    
    total_assets = general_assets + buffer_cash # 應該要 > 1000 萬
    total_liabilities = liabilities_df['金額'].sum()
    net_worth = total_assets + total_liabilities
    
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()
    
    # 計算「一般現金」有多少 (不含備援)
    normal_cash = general_assets_df[general_assets_df['類別'] == '現金']['金額'].sum()

    # --- 頂部指標區 ---
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("真實總資產", f"${total_assets/10000:,.0f} 萬", 
                help=f"一般資產 {general_assets/10000:.0f}萬 + 備援現金 {buffer_cash/10000:.0f}萬")
    
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    
    col3.metric("淨資產", f"${net_worth/10000:,.0f} 萬")
    
    col4.metric("🛡️ 抵利型備援現金", f"${buffer_cash/10000:,.0f} 萬", 
                delta="緊急預備金", delta_color="off")
    
    st.info(f"""
    **💡 資產結構檢查：**
    *   **一般活存現金**：${normal_cash/10000:,.0f} 萬 (生活費帳戶)
    *   **抵利型備援金**：${buffer_cash/10000:,.0f} 萬 (房貸抵扣用)
    *   **現金總水位**：**${(normal_cash + buffer_cash)/10000:,.0f} 萬**
    """)

    st.markdown("---")

    # --- 核心功能：GK + 股息 + 備援金 ---
    st.header("🌊 現金流與提領策略")

    st.sidebar.header("📊 參數設定")
    
    # 1. 收入參數
    st.sidebar.subheader("收入來源")
    honhai_eps = st.sidebar.number_input("鴻海預估配息 (元)", value=7.0, step=0.5)
    iwr = st.sidebar.number_input("GK 初始提領率 (%)", value=4.0, step=0.1) / 100
    
    # 2. 支出參數
    st.sidebar.subheader("支出與通膨")
    inflation_rate = st.sidebar.number_input("預估通膨率 (%)", value=2.0, step=0.1) / 100
    monthly_living = st.sidebar.number_input("純生活費 (月)", value=60000, step=5000)
    monthly_debt = st.sidebar.number_input("負債月付金 (房貸/信貸)", value=125000, step=5000)
    
    # --- 運算邏輯 (依照您的需求調整) ---
    
    # A. 支出
    annual_living_cost = monthly_living * 12 * (1 + inflation_rate)
    annual_debt_cost = monthly_debt * 12
    total_expense = annual_living_cost + annual_debt_cost

    # B. 收入 - 股息
    dividend_income = total_honhai_shares * honhai_eps
    
    # C. 收入 - 賣股 (GK 建議)
    # 邏輯：GK 算出的是「總提領金額」。
    # 需賣股金額 = GK總額 - 股息 (因為股息已經拿到了)
    # 如果 股息 > GK總額，則不賣股 (賣股=0)
    
    investment_debt = abs(total_liabilities)
    gk_base = max(0, general_assets - investment_debt) # GK 基數
    gk_total_limit = gk_base * iwr # GK 建議的年度總花費上限
    
    sell_stock_amount = max(0, gk_total_limit - dividend_income) # 實際需要賣股票換現金的錢
    
    # D. 可用總現金 (股息 + 賣股)
    total_available_cash = dividend_income + sell_stock_amount
    
    # E. 資金缺口 (由備援金支付)
    # 缺口 = 總支出 - 可用總現金
    shortfall = total_expense - total_available_cash
    buffer_usage = max(0, shortfall)
    
    # --- 版面顯示 ---
    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("📊 收支概況")
        st.write(f"鴻海股數: **{total_honhai_shares:,.0f}** 股")
        st.metric("1. 股息收入", f"${dividend_income:,.0f}", delta="第一層水源")
        st.metric("2. GK 補充提領 (賣股)", f"${sell_stock_amount:,.0f}", delta="第二層水源")
        st.metric("3. 總支出需求", f"${total_expense:,.0f}", delta_color="inverse")
        
        st.markdown("---")
        if buffer_usage > 0:
            st.error(f"⚠️ **現金流不足**")
            st.metric("需動用備援金", f"${buffer_usage:,.0f}", delta="第三層水源")
            survival_years = buffer_cash / buffer_usage
            st.write(f"抵利型帳戶可支撐： **{survival_years:.1f} 年**")
        else:
            surplus = total_available_cash - total_expense
            st.success(f"🎉 **現金流充裕**")
            st.metric("年度結餘", f"${surplus:,.0f}")

    with c2:
        st.subheader("🌊 資金瀑布圖 (Waterfall)")
        
        # 繪製邏輯：
        # 收入(綠) -> 賣股(綠) -> 支出(紅) -> 缺口(藍/備援)
        
        fig = go.Figure(go.Waterfall(
            name = "Cashflow", orientation = "v",
            measure = [
                "relative",   # 股息
                "relative",   # 賣股
                "total",      # 小計：手上現金
                "relative",   # 扣生活費
                "relative",   # 扣房貸
                "total"       # 結果：缺口(需動用備援)
            ],
            x = [
                "1. 股息收入", 
                "2. 賣股補足(GK)", 
                "可用現金小計", 
                "3. 生活費(含通膨)", 
                "4. 負債償還", 
                "資金缺口 (需動用備援)"
            ],
            textposition = "outside",
            text = [
                f"+{dividend_income/10000:.0f}萬", 
                f"+{sell_stock_amount/10000:.0f}萬", 
                f"={total_available_cash/10000:.0f}萬", 
                f"-{annual_living_cost/10000:.0f}萬",
                f"-{annual_debt_cost/10000:.0f}萬",
                f"-{buffer_usage/10000:.0f}萬" if buffer_usage > 0 else "0"
            ],
            y = [
                dividend_income, 
                sell_stock_amount, 
                0, # total row, auto calc
                -annual_living_cost, 
                -annual_debt_cost, 
                0  # total row
            ],
            connector = {"line":{"color":"rgb(63, 63, 63)"}},
            decreasing = {"marker":{"color":"#EF553B"}}, # 紅色 (支出)
            increasing = {"marker":{"color":"#00CC96"}}, # 綠色 (收入)
            totals = {"marker":{"color":"#1f77b4"}}      # 藍色 (總計/缺口)
        ))
        st.plotly_chart(fig, use_container_width=True)
        
        if buffer_usage > 0:
            st.warning("💡 圖表最右側的藍色柱子代表 **「不夠的錢」**，這筆錢將由您的**抵利型備援現金**自動填補。")

    # --- 資產圖表 ---
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
    st.write("資料讀取中... 若無顯示請檢查連線。")