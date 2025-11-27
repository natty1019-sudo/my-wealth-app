import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go  # <--- 補上這行就能修復錯誤了
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 設定頁面 ---
st.set_page_config(page_title="資產負債與現金流儀表板", layout="wide", page_icon="🏦")

# ==========================================
# 1. 資料處理核心 (升級版：增加讀取「股數」)
# ==========================================
def parse_my_data(raw_data):
    """
    解析您的資料格式，並嘗試讀取股數以便計算股息
    """
    assets = []
    liabilities = []
    
    section = "asset"
    
    for row in raw_data:
        # 補齊欄位長度，避免 list index out of range
        row = row + [''] * (5 - len(row))
        item_name = str(row[0]).strip()
        
        # --- 判斷區塊切換 ---
        if "資產合計" in item_name or "美金匯率" in item_name:
            section = "switch_to_liability_soon"
            continue
        
        if section == "switch_to_liability_soon" and ("房貸" in item_name or "信貸" in item_name or "借款" in item_name):
            section = "liability"

        if not item_name or item_name in ["項目", ""]: continue
        if "合計" in item_name or "淨值" in item_name: continue

        # --- 數值清理 ---
        def clean_num(x):
            if isinstance(x, (int, float)): return x
            x_str = str(x).replace(',', '').replace('NT$', '').replace('%', '').strip()
            return float(x_str) if x_str else 0

        try:
            # 邏輯 A: 資產區塊
            if section == "asset":
                # 金額通常在第 4 欄 (Index 3)
                amount = clean_num(row[3])
                # 股數通常在第 2 欄 (Index 1)，如果是現金則為 0
                shares = clean_num(row[1]) if row[1] else 0
                
                # 若金額抓不到，嘗試抓第 2 欄 (針對某些只填一欄的現金)
                if amount == 0 and shares > 10000 and "現金" in item_name: 
                    amount = shares
                    shares = 0
                
                # 自動分類
                category = "其他"
                if "現金" in item_name or "口袋" in item_name or "活存" in item_name: category = "現金"
                elif "美股" in item_name or "VT" in item_name or "VOO" in item_name or "TSLA" in item_name: category = "美股"
                elif "鴻海" in item_name or "0050" in item_name or "台股" in item_name: category = "台股"
                
                # 特別標記：抵利型 (備援現金)
                is_buffer = "抵利型" in item_name

                assets.append({
                    "類別": category, 
                    "項目": item_name, 
                    "金額": amount, 
                    "股數": shares,
                    "備援": is_buffer
                })

            # 邏輯 B: 負債區塊
            elif section == "liability":
                amount = clean_num(row[1])
                if amount > 0:
                    liabilities.append({"類別": "負債", "項目": item_name, "金額": -amount, "股數": 0, "備援": False})

        except ValueError:
            continue

    return pd.DataFrame(assets + liabilities)

# ==========================================
# 2. 連線 Google Sheets
# ==========================================
# 請確認您的 secrets.json 已經貼到 Streamlit Cloud 的 Secrets 設定中
try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 判斷是在雲端還是本地
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        # 本地測試用
        creds = ServiceAccountCredentials.from_json_keyfile_name('secrets.json', scope)
    
    client = gspread.authorize(creds)
    
    # *** 請修改這裡：換成您真正的試算表名稱 ***
    sheet = client.open("2024資產負債表").sheet1  # 假設您的表名是這個，且資料在第一個分頁
    # 如果您的表名不同，請修改上面那行引號內的文字
    
    raw_data_paste = sheet.get_all_values()
    df = parse_my_data(raw_data_paste)

except Exception as e:
    st.error(f"連線失敗，請檢查 API 設定或試算表名稱。錯誤訊息: {e}")
    # 發生錯誤時使用空 DataFrame 避免程式崩潰
    df = pd.DataFrame()

# ==========================================
# 3. 儀表板顯示邏輯
# ==========================================
st.title("🏦 資產配置與現金流戰情室")

if not df.empty:
    # --- 數據計算 ---
    assets_df = df[df['金額'] > 0]
    liabilities_df = df[df['金額'] < 0]
    
    total_assets = assets_df['金額'].sum()
    total_liabilities = liabilities_df['金額'].sum()
    net_worth = total_assets + total_liabilities
    
    # 提取「備援現金」(抵利型)
    buffer_cash_df = assets_df[assets_df['備援'] == True]
    buffer_cash = buffer_cash_df['金額'].sum()
    
    # 一般現金 (排除備援)
    normal_cash = assets_df[(assets_df['類別'] == '現金') & (assets_df['備援'] == False)]['金額'].sum()
    
    # 計算鴻海總股數 (用於股息試算)
    honhai_df = assets_df[assets_df['項目'].str.contains("鴻海")]
    total_honhai_shares = honhai_df['股數'].sum()

    # --- 1. 頂部關鍵指標 ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("淨資產 (Net Worth)", f"${net_worth/10000:,.0f} 萬")
    col2.metric("總負債 (Liabilities)", f"${total_liabilities/10000:,.0f} 萬", delta_color="inverse")
    
    # 顯示備援現金
    col3.metric("🛡️ 抵利型備援現金", f"${buffer_cash/10000:,.0f} 萬", 
                help="這是您的緊急預備金，不計入一般投資組合")
    
    # 槓桿率
    lv_ratio = abs(total_liabilities) / total_assets if total_assets > 0 else 0
    col4.metric("槓桿比率", f"{lv_ratio:.1%}", delta="偏高" if lv_ratio > 0.5 else "安全", delta_color="inverse")

    st.markdown("---")

    # --- 2. 股息現金流試算 (新功能) ---
    st.header("🌊 年度現金流試算 (股息 + 提領)")
    
    # 側邊欄：現金流參數
    st.sidebar.header("現金流參數")
    honhai_dps = st.sidebar.slider("預估鴻海股利 (元/股)", 0.0, 10.0, 5.5, 0.5)
    monthly_expense = st.sidebar.number_input("預估每月生活費 (元)", value=100000, step=5000)
    
    annual_expense = monthly_expense * 12
    
    # 計算預估股息
    estimated_dividend = total_honhai_shares * honhai_dps
    
    # 顯示現金流圖表
    c1, c2 = st.columns([1, 2])
    
    with c1:
        st.subheader("收入來源預估")
        st.write(f"持有鴻海股數: **{total_honhai_shares:,.0f}** 股")
        st.metric("預估年度股息", f"${estimated_dividend:,.0f}", delta=f"EPS設為 {honhai_dps}")
        
        # 安全氣囊存活時間
        survival_months = buffer_cash / monthly_expense if monthly_expense > 0 else 0
        st.info(f"🛡️ **安全氣囊分析**：\n\n您的「抵利型現金」(${buffer_cash/10000:.0f}萬) 可支撐 **{survival_months:.1f} 個月** 的生活費 (完全不賣股的情況下)。")

    with c2:
        st.subheader("GK 提領需求分析")
        
        # GK 參數
        iwr = st.sidebar.number_input("初始提領率 (%)", 3.0, 6.0, 4.0, 0.1) / 100
        
        # 淨投資部位 (扣除負債後的淨值 - 備援現金)
        # 邏輯：備援現金是保命錢，不拿來算 4% 提領；負債要先扣掉
        net_investable = net_worth - buffer_cash
        
        target_withdraw = net_investable * iwr
        
        # 缺口計算：目標提領 - 股息 = 實際需要賣出的資產
        gap = target_withdraw - estimated_dividend
        
        # 繪製瀑布圖 (Waterfall Chart) 顯示資金來源
        fig_waterfall = go.Figure(go.Waterfall(
            name = "20", orientation = "v",
            measure = ["relative", "relative", "total", "total"],
            x = ["預估股息收入", "需賣資產補足", "總提領現金", "年度生活費需求"],
            textposition = "outside",
            text = [f"{estimated_dividend/10000:.1f}萬", f"{gap/10000:.1f}萬", f"{target_withdraw/10000:.1f}萬", f"{annual_expense/10000:.1f}萬"],
            y = [estimated_dividend, gap, target_withdraw, annual_expense],
            connector = {"line":{"color":"rgb(63, 63, 63)"}},
        ))
        
        fig_waterfall.update_layout(title="資金來源 vs 生活支出", showlegend=False, height=350)
        st.plotly_chart(fig_waterfall, use_container_width=True)
        
        if target_withdraw > annual_expense:
            st.success(f"🎉 恭喜！依照 {iwr*100}% 提領率，資金充裕 (盈餘 ${target_withdraw - annual_expense:,.0f})")
        else:
            st.warning(f"⚠️ 注意：提領上限 (${target_withdraw:,.0f}) 低於生活費需求，需動用備援現金或降低支出。")

    st.markdown("---")

    # --- 3. 資產細節 (保留原本的功能) ---
    with st.expander("查看資產分佈細節"):
        st.dataframe(df)

else:
    st.info("正在等待連線或尚未讀取到資料...")