# Install required libraries in requirements.txt: streamlit, yfinance, pandas, requests, plotly
import pandas as pd
import yfinance as yf
import requests
import streamlit as st
from datetime import datetime, timedelta
import io
import plotly.graph_objects as go
import time
import pytz  # For IST timezone

# Function to fetch NSE symbols
def get_nse_symbols():
    nse_url = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
    response = requests.get(nse_url, headers={'User-Agent': 'Mozilla/5.0'})
    if response.status_code == 200:
        df = pd.read_csv(io.StringIO(response.text))
        symbols = df['SYMBOL'].apply(lambda x: f"{x}.NS").tolist()
        return symbols
    return []

# Function to fetch BSE symbols
def get_bse_symbols():
    bse_url = "https://api.bseindia.com/BseIndiaAPI/api/ListOfScripData/f/"
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.bseindia.com/', 'Origin': 'https://www.bseindia.com'}
    payload = {'statustype': 'A', 'scrip_grp': 'A,B,XT,X,XC,XD,Z,ZP,Y,F,T,MT,IF,IT,BE'}
    response = requests.post(bse_url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        if 'Table' in data:
            df = pd.DataFrame(data['Table'])
            symbols = df['scrip_id'].apply(lambda x: f"{x}.BO").tolist()
            return symbols
    return []

# Function to fetch stock data and filter by movement (intraday)
def get_stocks_with_movement(symbols, min_pct=3, max_pct=20, selected_date=None, sector_filter=None):
    if selected_date is None:
        now = datetime.now(pytz.timezone('Asia/Kolkata'))
        if now.hour < 9 or (now.hour == 9 and now.minute < 15) or now.hour > 15 or (now.hour == 15 and now.minute > 30):
            selected_date = (now - timedelta(days=1)).strftime('%Y-%m-%d')  # Previous day if market closed
        else:
            selected_date = now.strftime('%Y-%m-%d')  # Today for live

    try:
        data = yf.download(symbols, start=selected_date, end=selected_date, period='1d', interval='1m' if 'live' in st.session_state else '1d', progress=False)
        if data.empty:
            return pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            opens = data['Open']
            closes = data['Close']
            highs = data['High']
            lows = data['Low']
        else:
            opens = data[['Open']]
            closes = data[['Close']]
            highs = data[['High']]
            lows = data[['Low']]

        movements = ((highs - lows) / lows * 100).dropna(how='all')
        filtered = movements[(movements >= min_pct) & (movements <= max_pct)].dropna(how='all')

        result = []
        for symbol in filtered.columns:
            pct = filtered[symbol].iloc[-1] if not filtered[symbol].empty else None  # Latest value for live
            if pct is not None:
                # Basic sector mapping (expand with actual data)
                sector = 'Unknown'  # Placeholder; fetch from yf.Ticker(symbol).info.get('sector') if needed (slow for many)
                if sector_filter and sector != sector_filter:
                    continue
                result.append({
                    'Symbol': symbol,
                    'Movement (%)': round(pct, 2),
                    'Open': opens[symbol].iloc[0],
                    'High': highs[symbol].iloc[-1],
                    'Low': lows[symbol].iloc[-1],
                    'Close': closes[symbol].iloc[-1],
                    'Sector': sector
                })
        return pd.DataFrame(result)
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

# Streamlit App
st.title("Smart AI Trading Platform: Intraday Movement Scanner (NSE/BSE)")
st.markdown("""
Scan ~7000+ stocks for 3-20% intraday movements. Live updates during market hours (9:15 AM - 3:30 PM IST).
Data from yfinance. For educational use; trading involves risk.
""")

# Sidebar filters
st.sidebar.header("Filters")
min_pct = st.sidebar.slider("Min Movement %", 1, 10, 3)
max_pct = st.sidebar.slider("Max Movement %", 10, 50, 20)
selected_date = st.sidebar.date_input("Select Date", datetime.today() - timedelta(days=1))
sector_filter = st.sidebar.selectbox("Sector Filter", ["All", "IT", "Finance", "Energy", "Healthcare"])  # Expand options
auto_refresh = st.sidebar.checkbox("Auto-Refresh (every 5 min during market)", value=False)

if sector_filter == "All":
    sector_filter = None

# Session state for live mode
if 'live' not in st.session_state:
    st.session_state.live = False

# Fetch symbols once
if 'all_symbols' not in st.session_state:
    with st.spinner("Fetching symbols..."):
        nse_symbols = get_nse_symbols()
        bse_symbols = get_bse_symbols()
        st.session_state.all_symbols = list(set(nse_symbols + bse_symbols))
    st.write(f"Fetched {len(st.session_state.all_symbols)} unique symbols.")

# Scan button
if st.button("Scan Now (or Auto-Refreshing)"):
    with st.spinner("Scanning for movements..."):
        batch_size = 500
        results = []
        for i in range(0, len(st.session_state.all_symbols), batch_size):
            batch = st.session_state.all_symbols[i:i+batch_size]
            df_batch = get_stocks_with_movement(batch, min_pct, max_pct, selected_date.strftime('%Y-%m-%d'), sector_filter)
            if not df_batch.empty:
                results.append(df_batch)
        if results:
            final_df = pd.concat(results, ignore_index=True).sort_values('Movement (%)', ascending=False)
            st.subheader("Stocks with Selected Intraday Movement")
            st.dataframe(final_df.style.background_gradient(subset=['Movement (%)'], cmap='Greens'))

            # Interactive Chart for Top 5
            if not final_df.empty:
                top_5 = final_df.head(5)
                for _, row in top_5.iterrows():
                    st.subheader(f"{row['Symbol']} Chart")
                    ticker_data = yf.download(row['Symbol'], start=selected_date, period='1d', interval='5m')
                    fig = go.Figure(data=[go.Candlestick(x=ticker_data.index,
                                                         open=ticker_data['Open'],
                                                         high=ticker_data['High'],
                                                         low=ticker_data['Low'],
                                                         close=ticker_data['Close'])])
                    fig.update_layout(title=f"{row['Symbol']} Intraday", xaxis_rangeslider_visible=True)
                    st.plotly_chart(fig)

            # Download
            csv = final_df.to_csv(index=False)
            st.download_button("Download CSV", csv, "intraday_movements.csv", "text/csv")
        else:
            st.info("No stocks match criteria.")

# Auto-refresh logic
if auto_refresh:
    now_ist = datetime.now(pytz.timezone('Asia/Kolkata'))
    if 9 <= now_ist.hour <= 15 and (now_ist.hour != 15 or now_ist.minute <= 30):
        st.session_state.live = True
        time.sleep(300)  # 5 min
        st.experimental_rerun()
    else:
        st.info("Market closed; auto-refresh paused.")

st.markdown("### Notes: Run locally with `streamlit run app.py`. Deploy to Streamlit Cloud for web access.")