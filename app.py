import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client, Client

st.set_page_config(page_title="個人財務戰情室", layout="wide")

# === 🟢 初始化 Supabase 雲端連線 ===
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = init_supabase()

# === 🟢 建立 App 的登入記憶 ===
if "user" not in st.session_state:
    st.session_state.user = None

# === 🟢 登入與註冊介面 (守門員) ===
if st.session_state.user is None:
    st.title("🔐 歡迎來到專屬資產管理系統")
    st.write("請先登入或註冊帳號，系統將為您建立專屬且加密的資料庫。")

    # 🚀 終極改動 1：徹底移除容易在 iOS 當機的 st.tabs，改用單純的點擊選項
    login_mode = st.radio("選擇操作", ["登入", "註冊新帳號"], horizontal=True, label_visibility="collapsed")

    if login_mode == "登入":
        # 🚀 終極改動 2：加回 st.form，強迫系統抓取 Face ID 填入的資料
        with st.form(key="login_form"):
            login_email = st.text_input("信箱 (Email)", autocomplete="username")
            login_password = st.text_input("密碼 (Password)", type="password", autocomplete="current-password")
            submit_login = st.form_submit_button("登入", type="primary")

            if submit_login:
                try:
                    response = supabase.auth.sign_in_with_password({"email": login_email, "password": login_password})
                    st.session_state.user = response.user
                    st.rerun()
                except Exception as e:
                    st.error("登入失敗，請檢查帳號密碼。")

    else:
        with st.form(key="signup_form"):
            signup_email = st.text_input("註冊信箱 (Email)")
            signup_password = st.text_input("設定密碼 (至少 6 碼)", type="password")
            submit_signup = st.form_submit_button("註冊帳號")

            if submit_signup:
                try:
                    response = supabase.auth.sign_up({"email": signup_email, "password": signup_password})
                    st.success("🎉 註冊成功！請點擊上方選項切換回「登入」。")
                except Exception as e:
                    st.error(f"註冊失敗：{e}")

    st.stop() 

# ==================================================================
# 👇 登入成功後：讀取雲端資料與初始化
# ==================================================================

# 讀取使用者的雲端保險箱
if "data_loaded" not in st.session_state:
    response = supabase.table("user_data").select("data").eq("user_id", st.session_state.user.id).execute()
    
    # 如果雲端有資料，就用雲端的；沒有就用預設的
    if response.data and response.data[0]["data"]:
        cloud_data = response.data[0]["data"]
        st.session_state.debt_list = pd.DataFrame(cloud_data.get("debt_list", []))
        st.session_state.loan_data = cloud_data.get("loan_data", {"principal": 500000.0, "rate": 2.5, "periods": 60})
        st.session_state.custom_banks_v3 = pd.DataFrame(cloud_data.get("custom_banks_v3", []))
        st.session_state.portfolio = pd.DataFrame(cloud_data.get("portfolio", []))
        st.session_state.future_events = pd.DataFrame(cloud_data.get("future_events", []))
    else:
        # 預設資料 (新註冊的使用者會看到這個)
        st.session_state.debt_list = pd.DataFrame({"已結清": [False]*7, "項目": ["釜山行程超支", "Elantra 車輛花費", "露營裝備", "潛水裝備", "Garmin 手錶", "五月透支", "宮古島機酒"], "金額": [10661, 14955, 32339, 18570, 42780, 13000, 27460], "償還來源": ["七月分紅", "七月分紅", "七月分紅", "七月分紅", "七月分紅", "六月加班費", "八月分紅"]})
        st.session_state.loan_data = {"principal": 500000.0, "rate": 2.5, "periods": 60}
        st.session_state.custom_banks_v3 = pd.DataFrame({"功能標籤": ["一般活存"], "銀行名稱": ["渣打銀行"], "帳戶總額": [11111]})
        st.session_state.portfolio = pd.DataFrame({"市場": ["台股", "美股"], "股票代碼": ["2330.TW", "NVDA"], "持有股數": [321.0, 50.0], "投入本金": [445223.0, 5000.0]})   
        st.session_state.future_events = pd.DataFrame({"發生月份": ["第 1 個月", "第 1 個月", "第 2 個月", "第 10 個月"], "事件名稱": ["七月季分紅", "宮古島機酒扣款", "八月季分紅", "繳納牌照稅"], "金額": [140000, -27460, 140000, -7120]})
    
    st.session_state.data_loaded = True

# 側邊欄控制與儲存機制
st.sidebar.success(f"👤 目前登入：\n{st.session_state.user.email}")

st.sidebar.markdown("---")
# 🌟 雲端儲存按鈕
if st.sidebar.button("💾 儲存變更至雲端", type="primary"):
    with st.spinner("雲端同步中..."):
        # 將目前的狀態打包成字典
        current_data = {
            "debt_list": st.session_state.debt_list.to_dict('records'),
            "loan_data": st.session_state.loan_data,
            "custom_banks_v3": st.session_state.custom_banks_v3.to_dict('records'),
            "portfolio": st.session_state.portfolio.to_dict('records'),
            "future_events": st.session_state.future_events.to_dict('records')
        }
        # 覆蓋寫入 Supabase
        supabase.table("user_data").upsert({"user_id": st.session_state.user.id, "data": current_data}).execute()
    st.sidebar.success("✅ 已安全儲存！關閉網頁資料也不會遺失。")

st.sidebar.markdown("---")
if st.sidebar.button("登出"):
    supabase.auth.sign_out()
    st.session_state.user = None
    st.session_state.pop("data_loaded", None)
    st.rerun()

# ==================================================================
# 👇 系統核心介面 (不變)
# ==================================================================
st.title("💰 我的專屬資產管理系統")
tab1, tab2, tab3, tab4 = st.tabs(["📊 總覽儀表板", "🏦 12個月資金跑道", "📈 投資部位", "💳 帳戶與代墊"])

with tab1:
    st.subheader("本月財務快照")
    col1, col2, col3 = st.columns(3)
    col1.metric("中信可花費現金", "$250,000")
    col2.metric("聯邦待沖銷代墊", "$146,375", "-預計7/8月分紅沖銷")
    col3.metric("總投資現值", "$1,810,000", "+16.5%")

with tab2:
    st.subheader("🏦 12個月資金跑道 (動態預測)")
    col_in1, col_in2, col_in3 = st.columns(3)
    with col_in1: start_cash = st.number_input("本月初可動用現金", value=250000, step=10000)
    with col_in2: base_income = st.number_input("每月常規收入 (底薪+加班)", value=51698, step=1000)
    with col_in3: base_expense = st.number_input("每月固定支出", value=35000, step=1000)

    st.markdown("---")
    st.markdown("### 🔮 模擬未來大筆收支")
    month_options = [f"第 {i} 個月" for i in range(1, 13)]

    st.session_state.future_events = st.data_editor(
        st.session_state.future_events, num_rows="dynamic", use_container_width=True, hide_index=True,
       column_config={
            "發生月份": st.column_config.SelectboxColumn("發生月份", options=month_options, required=True),
            "事件名稱": st.column_config.TextColumn("事件名稱", required=True),
            "金額": st.column_config.NumberColumn("金額 (收入正數，支出負數)", default=0, step=1, format="$ %d")
        }, key="future_events_editor"
    )

    st.markdown("---")
    st.markdown("### 📊 12個月滾動水位預測")
    current_cash = start_cash
    runway_data = []
    for i in range(1, 13):
        month_label = f"第 {i} 個月"
        month_events = st.session_state.future_events[st.session_state.future_events["發生月份"] == month_label]
        if not month_events.empty:
            event_names = " + ".join(month_events["事件名稱"].dropna().astype(str).tolist())
            event_total = month_events["金額"].sum()
        else:
            event_names = "-"
            event_total = 0
        net_cash_flow = base_income - base_expense + event_total
        current_cash += net_cash_flow
        runway_data.append({"時間軸": month_label, "常規淨現金流": base_income - base_expense, "特殊事件": event_names, "特殊金額": event_total, "🏁 月底安全水位": current_cash})

    df_runway = pd.DataFrame(runway_data)
    st.dataframe(df_runway, column_config={"常規淨現金流": st.column_config.NumberColumn(format="$ %d"), "特殊金額": st.column_config.NumberColumn(format="$ %d"), "🏁 月底安全水位": st.column_config.NumberColumn(format="$ %d")}, hide_index=True, use_container_width=True)

with tab3:
    st.subheader("📈 投資部位與即時連線 ROI")
    st.info("💡 **股票代碼輸入指南**：美股直接輸入代碼（例 `NVDA`）、台股加 `.TW`（例 `2330.TW`）、加密貨幣輸入國際代碼（例 `BTC-USD`）")
    
    st.session_state.portfolio = st.data_editor(
        st.session_state.portfolio, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "市場": st.column_config.SelectboxColumn("市場", options=["台股", "美股", "加密貨幣"]),
            "股票代碼": st.column_config.TextColumn("股票代碼 (Ticker)"),
            "持有股數": st.column_config.NumberColumn("持有股數", step=1.0),
            "投入本金": st.column_config.NumberColumn("投入本金", step=1000.0, format="$ %d")
        }, key="portfolio_editor"
    )

    if st.button("🔄 更新最新即時報價與績效"):
        valid_stocks = st.session_state.portfolio.dropna(subset=["股票代碼"])
        valid_stocks = valid_stocks[valid_stocks["股票代碼"].str.strip() != ""]
        if valid_stocks.empty: st.warning("請先輸入股票代碼！")
        else:
            with st.spinner('連線全球交易所...'):
                cols = st.columns(3)
                total_invest = 0
                total_val = 0
                for i, (index, row) in enumerate(valid_stocks.iterrows()):
                    ticker_symbol = str(row["股票代碼"]).strip()
                    shares = float(row["持有股數"])
                    principal = float(row["投入本金"])
                    try:
                        ticker = yf.Ticker(ticker_symbol)
                        current_price = ticker.history(period="1d")['Close'].iloc[-1]
                        current_value = current_price * shares
                        total_invest += principal
                        total_val += current_value
                        roi = ((current_value - principal) / principal) * 100 if principal > 0 else 0
                        with cols[i % 3]:
                            st.markdown(f"#### 🏷️ {ticker_symbol}")
                            st.metric(label=f"現價: ${current_price:.2f} | 股數: {shares}", value=f"${current_value:,.0f}", delta=f"{roi:.2f}%")
                    except Exception:
                        with cols[i % 3]: st.error(f"無法抓取 {ticker_symbol}")
                st.markdown("---")
                st.subheader("📊 總體投資績效")
                overall_roi = ((total_val - total_invest) / total_invest) * 100 if total_invest > 0 else 0
                st.metric("總資產現值", f"${total_val:,.0f}", f"整體報酬率: {overall_roi:.2f}%")

with tab4:
    st.subheader("💳 多帳戶資金樞紐與代墊管理")
    with st.expander("⚙️ 銀行名稱與新增帳戶設定", expanded=True):
        col_name1, col_name2, col_name3 = st.columns(3)
        with col_name1: 
            hub1_label = st.text_input("自訂功能標籤 (1)", value="貸款與允用樞紐")
            bank_1_name = st.text_input(f"設定核心銀行 (1)", value="中信銀行")
        with col_name2: 
            hub2_label = st.text_input("自訂功能標籤 (2)", value="代墊與活存樞紐")
            bank_2_name = st.text_input(f"設定核心銀行 (2)", value="聯邦銀行")
        with col_name3: 
            hub3_label = st.text_input("自訂功能標籤 (3)", value="投資與交割樞紐")
            bank_3_name = st.text_input(f"設定核心銀行 (3)", value="國泰銀行")
        
        st.write("新增其他一般活存帳戶：")
        st.session_state.custom_banks_v3 = st.data_editor(
            st.session_state.custom_banks_v3, num_rows="dynamic", use_container_width=True, hide_index=True, 
            column_config={"帳戶總額": st.column_config.NumberColumn("帳戶總額", default=0, step=1, format="$ %d")}, key="custom_banks_editor_v3"
        )

    st.markdown("---")
    col_ctbc, col_union, col_cathay = st.columns(3)
    with col_ctbc:
        st.markdown(f"### 🏦 {bank_1_name}\n**{hub1_label}**") 
        ctbc_total = st.number_input("帳戶總金額 (a)", value=400000, step=1, key="ctbc_total")
        st.markdown("**📝 本息攤還計算機**")
        p = st.number_input("總借貸金額", value=st.session_state.loan_data["principal"], step=10000.0)
        r = st.number_input("年利率 (%)", value=st.session_state.loan_data["rate"], step=0.1)
        n = st.number_input("剩餘期數 (月)", value=st.session_state.loan_data["periods"], step=1)
        st.session_state.loan_data.update({"principal": p, "rate": r, "periods": n})
        
        monthly_rate = (r / 100) / 12
        monthly_pmt = p * (monthly_rate * (1 + monthly_rate)**n) / ((1 + monthly_rate)**n - 1) if (monthly_rate > 0 and n > 0) else (p / n if n > 0 else 0)
        st.info(f"👉 每月應繳款: **${monthly_pmt:,.0f}**")
        
        if st.button("✅ 本期已還款 (自動扣除本金)") and n > 0:
            st.session_state.loan_data["principal"] -= (monthly_pmt - (p * monthly_rate))
            st.session_state.loan_data["periods"] -= 1
            st.rerun()
        
        ctbc_reserve = st.number_input("🔒 預留貸款金額 (c)", value=int(monthly_pmt * 3), step=1)
        st.metric("✅ 允用花費金額 (b)", f"${ctbc_total - ctbc_reserve:,.0f}")

    with col_union:
        st.markdown(f"### 💳 {bank_2_name}\n**{hub2_label}**")
        union_total = st.number_input("帳戶總金額 (a)", value=250000, step=1, key="union_total")
        union_cc = st.number_input("本期信用卡繳款 (d)", value=8000, step=1)
        st.markdown("**📋 動態待沖銷清單 (c)**")
        st.session_state.debt_list = st.data_editor(st.session_state.debt_list, num_rows="dynamic", use_container_width=True, column_config={"金額": st.column_config.NumberColumn("金額", format="$%d")}, key="debt_editor")
        total_debt = st.session_state.debt_list[st.session_state.debt_list["已結清"] == False]["金額"].sum()
        st.error(f"🚨 待沖銷總計: ${total_debt:,.0f}")
        st.metric("✅ 活存現金流 (b)", f"${union_total - total_debt - union_cc:,.0f}")

    with col_cathay:
        st.markdown(f"### 🌳 {bank_3_name}\n**{hub3_label}**")
        cathay_total = st.number_input("帳戶總金額 (a)", value=180000, step=1, key="cathay_total")
        cathay_cc = st.number_input("本期信用卡繳款 (c)", value=25000, step=1, key="cathay_cc")
        st.metric("✅ 可投資金額 (b)", f"${cathay_total - cathay_cc:,.0f}")

    valid_extra_banks = st.session_state.custom_banks_v3.dropna(subset=["銀行名稱"])
    valid_extra_banks = valid_extra_banks[valid_extra_banks["銀行名稱"].str.strip() != ""]
    if not valid_extra_banks.empty:
        st.markdown("---")
        st.markdown("### 🏦 其他自訂帳戶總覽")
        extra_cols = st.columns(3)
        for i, (index, row) in enumerate(valid_extra_banks.iterrows()):
            with extra_cols[i % 3]:
                st.markdown(f"#### 💰 {row['銀行名稱']}\n**{row['功能標籤'] if pd.notna(row['功能標籤']) else '一般活存'}**") 
                st.metric("目前總額", f"${row['帳戶總額'] if pd.notna(row['帳戶總額']) else 0:,.0f}")