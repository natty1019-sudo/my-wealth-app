import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與現金流戰情室", layout="wide", page_icon="🛡️")

# ==========================================
# 1. 資料處理核心 (智慧辨識版：防止重複計算)
# ==========================================
def parse_my_data(raw_data):
    assets = []
    liabilities = []
    
    for row in raw_data:
        # 1. 補齊欄位，避免錯誤
        row = row + [''] * (5 - len(row))
        item_name = str(row[0]).strip()
        
        # 2. 【最關鍵修正】排除所有 "合計"、"淨值"、"匯率" 的行
        # 這樣就不會發生 (細項 + 合計) 導致金額變兩倍的情況
        if not item_name: continue
        if "合計" in item_name: continue 
        if "淨值" in item_name: continue
        if "匯率" in item_name: continue
        if item_name == "項目": continue

        # 3. 數值讀取 (掃描第2~4欄，抓取最大的數字)
        # 這樣無論您金額填在 B欄、C欄 還是 D欄，都能抓到
        def clean_num(x):
            if isinstance(x, (int, float)): return x
            x_str = str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()
            return float(x_str) if x_str else 0
        
        val_1 = clean_num(row[1]) # 第2欄
        val_2 = clean_num(row[2]) # 第3欄
        val_3 = clean_num(row[3]) # 第4欄
        
        # 取這三欄中最大的數字當作金額 (通常金額只有一欄有填)
        amount = max(val_1, val_2, val_3)
        
        # 4. 判斷它是「資產」還是「負債」 (依關鍵字)
        
        # --- A. 負債判斷 ---
        if ("房貸" in item_name or "信貸" in item_name or "借款" in item_name or "質押" in item_name):
            # 排除掉 "抵利型現金" (因為名字裡有房貸兩個字，但它是資產)
            if "現金" in item_name or "專戶" in item_name:
                pass # 這是資產，往下走
            else:
                if amount > 0:
                    liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "股數": 0, "備援": False})
                continue # 處理完負債，換下一行
        
        # --- B. 資產判斷 ---
        # 只要有錢的關鍵字，都算資產
        is_asset = False
        category = "其他"
        
        if "現金" in item_name or "活存" in item_name or "口袋" in item_name:
            is_asset = True
            category = "現金"
        elif "股票" in item_name or "ETF" in item_name or "鴻海" in item_name or "0050" in item_name:
            is_asset = True
            category = "台股"
        elif "美股" in item_name or "VT" in item_name or "VOO" in item_name:
            is_asset = True
            category = "美股"
            
        if is_asset and amount > 0:
            # 抓取股數 (通常在第2欄，且金額通常在第4欄，如果amount是從第4欄來的，那row[1]就是股數)
            shares = 0
            if amount == val_3: # 如果金額在第4欄
                shares = val_1  # 那股數就在第2欄
            
            # 標記備援
            is_buffer = "抵利型" in item_name

            assets.append({
                "類別": category, 
                "項目": item_name, 
                "金額": amount, 
                "股數": shares, 
                "備援": is_buffer
            })

    return pd.DataFrame(assets + liabilities)

# ==========================================
# 2. 資料來源
# ==========================================

# --- 模式 A: 驗證用數據 (模擬您的真實狀況) ---
# 這些加起來應該要是：資產 5848+652=6500萬 / 負債 3452萬
raw_data_paste = [
    ["鴻海股票（質押中）", "142000", "229.5", "32,589,000"],
    ["鴻海股票（可動用）", "80000", "229.5", "18,360,000"],
    ["0050 ETF", "20,000", "61.95", "1,239,000"],
    ["現金_一般活存", "", "", "6,292,969"], 
    ["✅ 資產合計", "", "", "58,480,969"], # 這一行程式會自動略過 (防止重複)
    ["", "", "", ""],
    ["富邦房貸", "11,540,000", "2.60%", ""],
    ["股票質押借款", "16,020,000", "2.41%", ""],
    ["其他信貸", "6,960,000", "", ""], 
    ["❌ 負債合計", "34,520,000", "", ""], # 這一行程式會自動略過 (防止變兩倍)
    ["", "", "", ""],
    ["現金_富邦_抵利型現金帳戶", "", "", "6,520,000"] # 這一行會被正確抓到
]

# --- 模式 B: 正式連線 Google Sheets ---
# ⚠️ 數字對了之後，請刪掉上面 raw_data_paste，並解開下面註解
# -------------------------------------------------------
# try:
#     scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
#     if "gcp_service_account" in st.secrets:
#         creds_dict = st.secrets["gcp_service_account"]
#         creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
#     else:
#         creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
#     client = gspread.authorize(creds)
#     
#     # *** 請確認這裡是您的試算表名稱 ***
#     sheet = client.open("2024資產負債表").sheet1 
#     raw_data_paste = sheet.get_all_values()
# except Exception as e:
#     st.error(f"連線失敗: {e}")
#     raw_data_paste = []
# -------------------------------------------------------

df = parse_my_data(raw_data_paste)

# ==========================================
# 3. 儀表板顯示
# ==========================================
st.title("🛡️ 資產配置與現金流戰情室")

if not df.empty:
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    # 數值計算
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum()
    
    general_assets_df = assets_df[assets_df['備援'] == False]
    general_assets = general_assets_df['金額'].sum()

    total_assets = general_assets + buffer_cash
    total_liabilities = liabilities_df['金額'].sum()
    net_worth = total_assets + total_liabilities
    
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()

    # --- 1. 關鍵指標 ---
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("總資產 (含備援)", f"${total_assets/10000:,.0f} 萬", 
                help=f"一般資產 {general_assets/10000:.0f}萬 + 備援現金 {buffer_cash/10000:.0f}萬")
    
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    
    col3.metric("淨資產", f"${net_worth/10000:,.0f} 萬")
    
    lv_ratio = abs(total_liabilities) / total_assets if total_assets > 0 else 0
    col4.metric("總槓桿比率", f"{lv_ratio:.1%}", delta_color="inverse")

    # --- 2. 核心分析區 ---
    st.header("🌊 年度現金流與提領策略")

    # 參數設定
    st.sidebar.header("參數設定")
    honhai_eps = st.sidebar.number_input("鴻海預估配息 (元)", value=7.0, step=0.5)
    iwr = st.sidebar.number_input("GK 初始提領率 (%)", value=4.0, step=0.1) / 100
    monthly_expense = st.sidebar.number_input("預估月生活費", value=100000, step=10000)
    
    annual_expense = monthly_expense * 12
    estimated_dividend = total_honhai_shares * honhai_eps
    
    # GK 提領基數：(一般資產 - 總負債)
    investment_debt = abs(total_liabilities) 
    base_for_gk = max(0, general_assets - investment_debt)
    
    target_withdraw = base_for_gk * iwr
    gap = target_withdraw - estimated_dividend

    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("📊 收入來源預估")
        st.write(f"鴻海股數: **{total_honhai_shares:,.0f}** 股")
        st.metric("1. 預估股息", f"${estimated_dividend:,.0f}")
        st.metric("2. GK 建議提領", f"${target_withdraw:,.0f}", help="基數 = 一般資產 - 總負債")
        
        st.info(f"🛡️ **抵利型備援**：${buffer_cash/10000:,.0f} 萬\n\n可支撐 **{buffer_cash/monthly_expense:.1f} 個月**")

    with c2:
        st.subheader("🌊 資金瀑布圖")
        
        fig = go.Figure(go.Waterfall(
            name = "Cashflow", orientation = "v",
            measure = ["relative", "relative", "total", "total", "relative"],
            x = ["股息收入", "需賣資產", "可提領總額", "年度生活費", "結餘/透支"],
            textposition = "outside",
            text = [
                f"+{estimated_dividend/10000:.0f}萬", 
                f"+{gap/10000:.0f}萬", 
                f"={target_withdraw/10000:.0f}萬", 
                f"-{annual_expense/10000:.0f}萬",
                f"{(target_withdraw - annual_expense)/10000:.0f}萬"