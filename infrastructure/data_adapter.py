import pandas as pd
import yfinance as yf
from datetime import date


class MarketDataAdapter:
    @staticmethod
    def fetch_historical_data(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
        df = yf.download(ticker, start=start_date, end=end_date, auto_adjust=False)
        
        if df.empty:
            raise ValueError("No data found for the given ticker and date range")
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        
        df = df[['Open', 'High', 'Low', 'Close']].dropna()
        return df
