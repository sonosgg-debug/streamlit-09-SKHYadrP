import os
import datetime
import re
import logging
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DEFAULT_START_DATE = datetime.date(2026, 7, 13)

def download_ticker_yf(ticker: str, start_date: datetime.date, end_date: datetime.date) -> pd.Series:
    """
    yfinance를 통해 티커의 종가(Close) 데이터를 다운로드합니다.
    """
    # yfinance end_date는 exclusive이므로 +1일
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = (end_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    
    logging.info(f"yfinance 다운로드: {ticker} ({start_str} ~ {end_str})")
    try:
        df = yf.download(ticker, start=start_str, end=end_str, progress=False)
        if df.empty:
            logging.warning(f"{ticker} 데이터가 비어있습니다.")
            return pd.Series(dtype=float, name=ticker)
            
        if isinstance(df.columns, pd.MultiIndex):
            if 'Close' in df.columns.levels[0]:
                ticker_cols = [c for c in df['Close'].columns if ticker in c or c in ticker]
                if ticker_cols:
                    s = df['Close'][ticker_cols[0]]
                else:
                    s = df['Close'].iloc[:, 0]
            else:
                s = df.iloc[:, 0]
        else:
            if 'Close' in df.columns:
                s = df['Close']
            else:
                s = df.iloc[:, 0]
                
        s = s.dropna()
        s.index = pd.to_datetime(s.index).date
        s.name = ticker
        return s
    except Exception as e:
        logging.error(f"yfinance 다운로드 실패 ({ticker}): {e}")
        return pd.Series(dtype=float, name=ticker)

def download_naver_sise(code: str, start_date: datetime.date, end_date: datetime.date) -> pd.Series:
    """
    네이버 금융 일별시세에서 국내 종목 코드의 종가를 크롤링합니다 (Fallback용).
    """
    logging.info(f"네이버 금융 다운로드: {code} ({start_date} ~ {end_date})")
    dates = []
    closes = []
    page = 1
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    
    while page <= 40:
        url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page={page}"
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code != 200:
                break
            soup = BeautifulSoup(res.text, 'html.parser')
            table = soup.find('table', class_='type2')
            if not table:
                break
            rows = table.find_all('tr')
            page_has_data = False
            reached_start = False
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 7:
                    d_text = cells[0].text.strip()
                    c_text = cells[1].text.strip().replace(',', '')
                    if d_text and c_text:
                        dt = datetime.datetime.strptime(d_text, '%Y.%m.%d').date()
                        if dt < start_date:
                            reached_start = True
                            break
                        if dt <= end_date:
                            dates.append(dt)
                            closes.append(float(c_text))
                            page_has_data = True
            if reached_start or not page_has_data:
                break
            page += 1
        except Exception as e:
            logging.error(f"네이버 금융 파싱 에러 (page {page}): {e}")
            break
            
    if not dates:
        return pd.Series(dtype=float, name=code)
        
    s = pd.Series(closes, index=dates, name=code).sort_index()
    s = s[~s.index.duplicated(keep='first')]
    return s

def fetch_skhy_data(start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    """
    SKHY, KRW=X(환율), SK하이닉스(000660) 데이터를 수집하고
    정합성 정제 및 원화 환산, 프리미엄을 계산한 통합 DataFrame을 반환합니다.
    """
    # 1. 미국 SKHY 주가
    s_skhy = download_ticker_yf('SKHY', start_date, end_date)
    
    # 2. USD/KRW 원달러 환율
    s_krw = download_ticker_yf('KRW=X', start_date, end_date)
    
    # 3. 국내 SK하이닉스 주가 (yfinance 우선, 누락 시 네이버 금융 폴백)
    s_sk = download_ticker_yf('000660.KS', start_date, end_date)
    if s_sk.empty or len(s_sk) < 5:
        logging.info("SK하이닉스 yfinance 데이터 불충분으로 네이버 금융 수집 시도...")
        s_naver = download_naver_sise('000660', start_date, end_date)
        if not s_naver.empty:
            s_sk = s_naver

    # 4. 결합 및 전처리
    df = pd.concat([s_skhy, s_krw, s_sk], axis=1)
    df.columns = ['SKHY_USD', 'USDKRW', 'SK_KRW']
    
    # 두 주식 시장 중 최소 한 곳이라도 개장한 날 보존
    df = df.dropna(subset=['SKHY_USD', 'SK_KRW'], how='all')
    
    # 시계열 오름차순 정렬 후 양국 공휴일/영업일 차이 Forward Fill
    df = df.sort_index(ascending=True)
    df = df.ffill()
    # 시작 시점 이전 NaN 제거
    df = df.dropna(subset=['SKHY_USD', 'USDKRW', 'SK_KRW'])
    
    # 날짜 범위 엄격 필터링
    df = df[(df.index >= start_date) & (df.index <= end_date)]
    
    # 5. 지표 계산
    # 공식 2: SKHY(원화) = 달러 기준 주가 * 10 * 당일 환율
    df['SKHY_KRW'] = df['SKHY_USD'] * 10.0 * df['USDKRW']
    
    # 공식 3: 프리미엄 금액 및 백분율(%)
    # 프리미엄 금액 = SKHY(원화) - SK하이닉스(원)
    df['Premium_KRW'] = df['SKHY_KRW'] - df['SK_KRW']
    # 프리미엄 % = ((SKHY(원화) - SK하이닉스) / SK하이닉스) * 100
    df['Premium_Pct'] = (df['Premium_KRW'] / df['SK_KRW']) * 100.0

    return df

def get_summary_stats(df: pd.DataFrame) -> dict:
    """
    대시보드 KPI 카드 및 통계 요약을 생성합니다.
    """
    if df.empty:
        return {}
        
    latest_row = df.iloc[-1]
    prev_row = df.iloc[-2] if len(df) >= 2 else latest_row
    
    latest_date = df.index[-1]
    sk_krw = latest_row['SK_KRW']
    skhy_usd = latest_row['SKHY_USD']
    usdkrw = latest_row['USDKRW']
    skhy_krw = latest_row['SKHY_KRW']
    premium_krw = latest_row['Premium_KRW']
    premium_pct = latest_row['Premium_Pct']
    
    prev_premium_pct = prev_row['Premium_Pct']
    delta_premium_pct = premium_pct - prev_premium_pct
    
    avg_premium = df['Premium_Pct'].mean()
    max_premium = df['Premium_Pct'].max()
    min_premium = df['Premium_Pct'].min()
    
    max_date = df['Premium_Pct'].idxmax()
    min_date = df['Premium_Pct'].idxmin()

    return {
        'latest_date': latest_date,
        'sk_krw': sk_krw,
        'skhy_usd': skhy_usd,
        'usdkrw': usdkrw,
        'skhy_krw': skhy_krw,
        'premium_krw': premium_krw,
        'premium_pct': premium_pct,
        'delta_premium_pct': delta_premium_pct,
        'avg_premium': avg_premium,
        'max_premium': max_premium,
        'min_premium': min_premium,
        'max_date': max_date,
        'min_date': min_date,
        'data_count': len(df)
    }

if __name__ == '__main__':
    today = datetime.date.today()
    print(f"테스트 데이터 수집: {DEFAULT_START_DATE} ~ {today}")
    result_df = fetch_skhy_data(DEFAULT_START_DATE, today)
    print("결과 샘플:")
    print(result_df.tail())
    stats = get_summary_stats(result_df)
    print("통계 요약:", stats)
