import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與現金流戰情室", layout="wide", page_icon="🛡️")

# ==========================================
# 1. 資料處理核心 (修正版：確保讀取到底部)
# ==========================================
def parse_my_data(raw_data):
    assets = []
    liabilities = []
    section = "asset"
    
    for row in raw_data:
        # 補齊欄位長度
        row = row + [''] * (5 - len(row))
        item_name = str(row[0]).strip()
        
        # --- 判斷區塊切換 ---
        # 只要碰到這類關鍵字，就切換到負債模式
        if "房貸" in item_name or "信貸" in item_name or "借款" in item_name or "負債" in item_name:
            if "合計" not in item_name: # 避免標題行誤判
                section = "liability"
        
        # 如果這一行是 "資產合計" 或 "匯率"，先跳過，但不要停止讀取
        if "資產合計" in item_name or "美金匯率" in item_name or "淨值" in item_name:
            continue

        # 略過空行
        if not item_name or item_name in ["項目", ""]: continue

        # --- 數值清理 ---
        def clean_num(x):
            if isinstance(x, (int, float)): return x
            x_str = str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()
            return float(x_str) if x_str else 0

        try:
            # 判斷是資產還是負債
            # 特例：如果項目名稱包含 "抵利型" 或 "現金"，即使在下方也算資產
            current_type = section
            if "抵利型" in item_name and "房貸" not in item_name: current_type = "asset" # 抵利型現金是資產
            if "抵利型" in item_name and "房貸" in item_name: current_type = "liability" # 抵利型房貸是負債
            if "現金" in item_name: current_type = "asset"

            if current_type == "asset":
                amount = clean_num(row[3]) # 預設抓第4欄
                shares = clean_num(row[1]) if row[1] else 0
                
                # 修正：若金額為0但數字填在第2欄 (常見於現金行)
                if amount == 0 and shares > 10000: 
                    amount = shares
                    shares = 0
                
                # 自動分類
                category = "其他"
                if "現金" in item_name or "口袋" in item_name or "活存" in item_name: category = "現金"
                elif "美股" in item_name or "VT" in item_name or "VOO" in item_name or "TSLA" in item_name: category = "美股"
                elif "鴻海" in item_name or "0050" in item_name or "台股" in item_name: category = "台股"
                
                # [關鍵] 標記備援現金
                is_buffer = "抵利型" in item_name

                assets.append({"類別": category, "項目": item_name, "金額": amount, "股數": shares, "備援": is_buffer})

            elif current_type == "liability":
                amount = clean_num(row[1]) # 負債金額通常在第2欄
                # 若第2欄沒抓到，試試第3或4欄 (防止格式跑掉)
                if amount == 0: amount = clean_num(row[2])
                if amount == 0: amount = clean_num(row[3])

                if amount > 0:
                    liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "股數": 0, "備援": False})
        except ValueError:
            continue
            
    return pd.DataFrame(assets + liabilities)

# ==========================================
# 2. 資料來源 (已修正為您的真實數字結構)
# ==========================================

# --- 模式 A: 測試數據 (根據您提供的 5848萬 / 3452萬 / 652萬 設定) ---
# ⚠️ 這組數據是為了讓您現在馬上能看到正確的加總
raw_data_paste = [
    ["鴻海股票（質押中）", "142000", "229.5", "32,589,000"],
    ["鴻海股票（可動用）", "80000", "229.5", "18,360,000"],
    ["0050 ETF", "20,000", "61.95", "1,239,000"],
    ["美股資產", "", "", "4,000,000"],
    ["一般現金", "", "", "2,292,969"],
    ["✅ 資產合計 (不含抵利型)", "", "", "58,480,969"], # 這是您原本表格的資產總數
    ["", "", "", ""],
    ["富邦房貸", "11,540,000", "2.60%", ""],
    ["股票質押借款", "16,020,000", "2.41%", ""],
    ["其他信貸", "6,960,000", "", ""], 
    ["❌ 負債合計", "34,520,000", "", ""], # 這是您的負債總數
    ["", "", "", ""],
    ["🧾 淨值", "", "", ""],
    ["現金_富邦_抵利型現金帳戶", "", "", "6,520,000"] # 這是原本被漏掉的備援金
]

# --- 模式 B: 正式連線 Google Sheets ---
# ⚠️ 確認數字正確後，請刪掉上面 raw_data_paste，並解開下面註解
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
# 3. 儀表板顯示邏輯
# ==========================================
st.title("🛡️ 資產配置與現金流戰情室")

if not df.empty:
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    # 數值計算
    # 備援現金
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum()
    
    # 一般資產 (扣除備援)
    general_assets_df = assets_df[assets_df['備援'] == False]
    general_assets = general_assets_df['金額'].sum()

    # 真實總資產 = 一般資產 + 備援現金
    total_assets = general_assets + buffer_cash
    
    total_liabilities = liabilities_df['金額'].sum()
    net_worth = total_assets + total_liabilities # 負債為負值，所以直接相加
    
    # 鴻海股數
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()

    # --- 1. 關鍵指標 ---
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("真實總資產", f"${total_assets/10000:,.0f} 萬", 
                help=f"一般資產 {general_assets/10000:.0f}萬 + 備援現金 {buffer_cash/10000:.0f}萬")
    
    col2.metric("總負債", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    
    col3.metric("淨資產 (Net Worth)", f"${net_worth/10000:,.0f} 萬", 
                delta=f"含備援: {buffer_cash/10000:.0f}萬")
    
    # 槓桿率
    lv_ratio = abs(total_liabilities) / total_assets if total_assets > 0 else 0
    col4.metric("總槓桿比率", f"{lv_ratio:.1%}", delta_color="inverse")

    st.info(f"""
    **💡 數據核對：** 
    目前程式讀取到：一般投資資產 **${general_assets:,.0f}** 
    + 抵利型備援現金 **${buffer_cash:,.0f}** 
    = **總資產 ${total_assets:,.0f}**
    """)

    st.markdown("---")

    # --- 2. 核心分析區 ---
    st.header("🌊 年度現金流與提領策略")

    # 參數設定
    st.sidebar.header("參數設定")
    honhai_eps = st.sidebar.number_input("鴻海預估配息 (元)", value=7.0, step=0.5)
    iwr = st.sidebar.number_input("GK 初始提領率 (%)", value=4.0, step=0.1) / 100
    monthly_expense = st.sidebar.number_input("預估月生活費", value=100000, step=10000)
    
    # 計算邏輯
    annual_expense = monthly_expense * 12
    estimated_dividend = total_honhai_shares * honhai_eps
    
    # GK 提領基數：只用「一般投資資產」，不包含備援金
    # 如果您認為負債要先扣掉再算提領，請使用 net_investable
    # 這裡採用較保守的邏輯：(一般資產 - 投資型負債)
    investment_debt = abs(total_liabilities) 
    base_for_gk = max(0, general_assets - investment_debt)
    
    # 修正：若扣除負債後基數太小，顯示警告，但不讓程式崩潰
    if base_for_gk == 0:
        target_withdraw = 0
        gap = 0
        st.error("⚠️ 警告：您的總負債高於一般投資資產，GK 提領基數為 0。建議優先處理債務。")
    else:
        target_withdraw = base_for_gk * iwr
        gap = target_withdraw - estimated_dividend

    # 版面配置
    c1, c2 = st.columns([1, 2])

    with c1:
        st.subheader("📊 收入來源預估")
        st.write(f"鴻海股數合計: **{total_honhai_shares:,.0f}** 股")
        st.metric("1. 預估股息收入", f"${estimated_dividend:,.0f}", delta=f"EPS: {honhai_eps}元")
        st.metric("2. GK 建議提領", f"${target_withdraw:,.0f}", help="基數 = 一般資產 - 總負債")
        
        st.markdown(f"""
        **🛡️ 抵利型備援池**
        目前水位：`${buffer_cash:,.0f}`
        可支撐生活： **{buffer_cash/monthly_expense:.1f} 個月**
        *(不賣股、不領息狀況下)*
        """)

    with c2:
        st.subheader("🌊 資金瀑布圖 (Waterfall)")
        
        fig = go.Figure(go.Waterfall(
            name = "Cashflow", orientation = "v",
            measure = ["relative", "relative", "total", "total", "relative"],
            x = ["股息收入", "需賣資產補足", "可提領現金總額", "年度生活費", "結餘/透支"],
            textposition = "outside",
            text = [
                f"+{estimated_dividend/10000:.0f}萬", 
                f"+{gap/10000:.0f}萬", 
                f"={target_withdraw/10000:.0f}萬", 
                f"-{annual_expense/10000:.0f}萬",
                f"{(target_withdraw - annual_expense)/10000:.0f}萬"
            ],
            y = [
                estimated_dividend, 
                gap, 
                target_withdraw, 
                -annual_expense, 
                (target_withdraw - annual_expense)
            ],
            connector = {"line":{"color":"rgb(63, 63, 63)"}},
            decreasing = {"marker":{"color":"#EF553B"}},
            increasing = {"marker":{"color":"#00CC96"}},
            totals = {"marker":{"color":"#1f77b4"}}
        ))
        
        fig.update_layout(title="資金來源 vs 支出結構", height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    
    # --- 3. 資產細節與分佈 ---
    with st.expander("查看資產負債明細"):
        st.dataframe(df)

else:
    st.write("資料讀取中...")