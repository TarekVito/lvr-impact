import streamlit as st
import pandas as pd
from datetime import date

from domain.constants import ASSET_TICKER
from domain.calculations import calculate_target_units
from domain.models import SimulationParams
from application.simulation_service import SimulationService
from infrastructure.data_adapter import MarketDataAdapter
from infrastructure.ui.components import UIComponents


def main():
    UIComponents.render_header()
    UIComponents.render_explanation()

    st.sidebar.header("Strategy Inputs")
    capital_input = st.sidebar.number_input(
        "Initial Capital ($)", 
        min_value=1000.0, 
        value=10000.0, 
        step=1000.0,
        help="Your starting cash for the simulation."
    )
    max_drop_input = st.sidebar.slider(
        "Max Market Drop to Survive (%)", 
        min_value=10.0, 
        max_value=70.0, 
        value=30.0, 
        step=1.0,
        help="The size of the market crash you want to survive. "
             "A higher % means fewer units and less risk."
    )

    rebalance_frequency = st.sidebar.selectbox(
        "Rebalancing Frequency",
        options=["Never", "Daily", "Monthly", "Quarterly"],
        index=0,
        help=(
            "How often to rebalance your position to the risk target. "
            "'Never' is a static 'buy and hold' of the initial units. "
            "'Daily' is the most aggressive (and riskiest). "
            "'Monthly' or 'Quarterly' are common alternatives."
        )
    )

    st.sidebar.header("Backtest Period")
    min_allowed_date = pd.to_datetime("1950-01-01").date()
    max_allowed_date = date.today()

    start_date = st.sidebar.date_input(
        "Start Date", 
        pd.to_datetime("2010-01-01"),
        min_value=min_allowed_date,
        max_value=max_allowed_date
    )
    end_date = st.sidebar.date_input(
        "End Date", 
        max_allowed_date,
        min_value=min_allowed_date,
        max_value=max_allowed_date
    )

    if st.sidebar.button("Run Backtest", type="primary"):
        params = SimulationParams(
            capital=capital_input,
            max_drop_percent=max_drop_input,
            rebalance_frequency=rebalance_frequency,
            start_date=start_date,
            end_date=end_date
        )
        
        with st.spinner(f"Fetching {ASSET_TICKER} data..."):
            data = MarketDataAdapter.fetch_historical_data(
                ASSET_TICKER, 
                params.start_date, 
                params.end_date
            )
        
        entry_price_raw = data.iloc[0]['Open']
        entry_price = entry_price_raw.iloc[0] if isinstance(entry_price_raw, pd.Series) else entry_price_raw

        initial_units = calculate_target_units(
            params.capital, 
            entry_price, 
            params.max_drop_percent
        )
        
        st.header("Backtest Results")
        
        simulation_service = SimulationService()
        
        with st.spinner("Running leveraged simulation..."):
            results_df, leveraged_summary = simulation_service.run_leveraged_simulation(
                params.capital, 
                initial_units, 
                entry_price, 
                data,
                params.rebalance_frequency,
                params.max_drop_percent
            )
        
        with st.spinner("Running benchmark simulation..."):
            benchmark_df, benchmark_summary = simulation_service.run_benchmark_simulation(
                params.capital,
                entry_price,
                data
            )
        
        results_df['Benchmark Equity'] = benchmark_df['Equity']

        UIComponents.render_performance_summary(leveraged_summary, benchmark_summary)
        UIComponents.render_equity_comparison_chart(results_df)
        UIComponents.render_risk_analysis_chart(results_df)
        UIComponents.render_additional_charts(results_df, data)
        UIComponents.render_raw_data(results_df, data)
    else:
        st.info("Click 'Run Backtest' in the sidebar to start the simulation.")


if __name__ == "__main__":
    main()
