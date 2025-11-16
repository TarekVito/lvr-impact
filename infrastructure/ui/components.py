import streamlit as st
import pandas as pd
import altair as alt
from domain.models import SimulationResult, BenchmarkResult
from domain.constants import ASSET_TICKER


class UIComponents:
    @staticmethod
    def render_header():
        st.set_page_config(layout="wide")
        st.title("📈 Leveraged Survival Strategy Backtester")
        st.markdown(f"""
            This app backtests the **"Leveraged Survival Strategy"** against a 
            **"Simple Buy & Hold"** benchmark.
            Both strategies are tested on **{ASSET_TICKER}**.
        """)

    @staticmethod
    def render_explanation():
        with st.expander("How this Simulator Works (And What The Inputs Mean)", expanded=False):
            st.markdown(
                """
                This tool backtests the "Leveraged Survival Strategy" against real historical data
                and compares it to a simple, unleveraged "Buy and Hold" strategy.
                
                ### The Two Strategies
                
                1.  **Leveraged Survival Strategy (Blue Line)**:
                    * **Goal:** To survive a pre-determined market crash (e.g., 30%)
                        without being liquidated.
                    * **Calculation:** You use the inputs on the sidebar to calculate the
                        maximum number of *leveraged* units you can buy.
                    * **Risks:** This strategy is subject to **Liquidation** (if the
                        market drops *more* than you planned for) and **Daily Holding Costs**
                        (the "slow bleed" from fees).
                
                2.  **Simple Buy & Hold (Benchmark) (Red Line)**:
                    * **Goal:** To show what happens if you just buy the asset
                        with no leverage.
                    * **Calculation:** `Units = Initial Capital / Entry Price`.
                    * **Risks:** There is no liquidation risk and no daily costs.
                        Your only risk is that the asset's price goes down.
                
                ---
                
                ### The Input Parameters
                
                #### 1. Initial Capital ($)
                This is your starting cash. It's used as the starting equity for *both*
                strategies, ensuring a fair comparison.
                
                #### 2. Max Market Drop to Survive (%)
                This is the **most important input** for the *Leveraged Strategy*.
                
                * It is **NOT** a 30% stop-loss.
                * It is the size of a market crash (e.g., 30%) you want your leveraged
                    position to **survive** without being liquidated by the broker.
                * A *higher* number here means you'll buy *fewer* leveraged units,
                    making the strategy safer.
                    
                #### 3. Enable Dynamic Risk Rebalancing
                This is an **advanced strategy option** that changes how the leveraged position behaves:
                
                * **OFF (Default):** You calculate your position size once at the start and hold it.
                    This is the "Day 1" aggressive approach that ignores future fees in the buffer calculation.
                * **ON (Advanced):** The simulation recalculates your target units **daily** to maintain
                    a constant risk buffer. This creates a "Constant Risk" strategy.
                
                **⚠️ WARNING about Dynamic Rebalancing:**
                * **Buy High:** As markets rally, you'll be forced to ADD to your position at higher prices.
                * **Sell Low:** As markets drop, you'll be forced to REDUCE your position at lower prices.
                * **Result:** This can be very profitable in strong bull markets but extremely costly
                    in choppy/sideways markets due to constant "whipsawing".
                
                #### 4. Backtest Period (Start/End Date)
                This is the historical window for the simulation.
                
                * **Start Date:** Both strategies "buy" their units at the 'Open'
                    price of this day.
                * **End Date:** The simulation stops on this day (unless the leveraged
                    position is liquidated first).
                """
            )

    @staticmethod
    def render_performance_summary(leveraged_result: SimulationResult, 
                                   benchmark_result: BenchmarkResult):
        if leveraged_result.liquidated:
            st.error(f"❌ **LEVERAGED STRATEGY LIQUIDATED** on {leveraged_result.liquidation_date.strftime('%Y-%m-%d')}")
        else:
            st.success("✅ **LEVERAGED STRATEGY SURVIVED** - Position was not liquidated.")
            
        st.subheader("Strategy Performance Summary")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Leveraged Survival Strategy")
            c1, c2 = st.columns(2)
            c1.metric("Initial Units", f"{leveraged_result.initial_units:.4f}")
            c2.metric("Total Costs Paid", f"${leveraged_result.total_costs_paid:,.2f}")
            c1.metric("Final Equity", f"${leveraged_result.final_equity:,.2f}")
            c2.metric("Total Return", f"{leveraged_result.total_return_pct:,.2f}%")

        with col2:
            st.markdown("#### Simple Buy & Hold (Benchmark)")
            c3, c4 = st.columns(2)
            c3.metric("Initial Units", f"{benchmark_result.units_held:.4f}")
            c4.metric("Total Costs Paid", "$0.00")
            c3.metric("Final Equity", f"${benchmark_result.final_equity:,.2f}")
            c4.metric("Total Return", f"{benchmark_result.total_return_pct:,.2f}%")

    @staticmethod
    def render_equity_comparison_chart(results_df: pd.DataFrame):
        chart_data_long = results_df.reset_index().rename(
            columns={'index': 'Date'}
        ).melt(
            id_vars=['Date', 'Units Held', 'Unit Change', 'Rebalance Action'], 
            value_vars=['Leveraged Equity', 'Benchmark Equity'],
            var_name='Strategy', 
            value_name='Equity'
        )
        
        base = alt.Chart(chart_data_long).encode(
            x=alt.X('Date:T', axis=alt.Axis(title='Date', format="%Y-%m-%d")),
        ).interactive()

        line_chart = base.mark_line(interpolate='linear').encode(
            y=alt.Y('Equity:Q', title='Equity ($)'),
            color=alt.Color('Strategy:N', title='Strategy'),
            tooltip=[
                alt.Tooltip('Date:T', format="%Y-%m-%d"),
                alt.Tooltip('Strategy:N'),
                alt.Tooltip('Equity:Q', format=',.2f'),
                alt.Tooltip('Units Held:Q', format='.4f'),
                alt.Tooltip('Rebalance Action:N'),
                alt.Tooltip('Unit Change:Q', format='.4f')
            ]
        )

        action_data = results_df.reset_index().rename(
            columns={'index': 'Date'}
        ).query("`Rebalance Action` != 'Hold'")

        buy_points = alt.Chart(action_data.query("`Rebalance Action` == 'Buy'")).mark_point(
            shape='triangle', 
            size=80, 
            color='green',
            filled=True
        ).encode(
            x=alt.X('Date:T'),
            y=alt.Y('Leveraged Equity:Q'),
            tooltip=[
                alt.Tooltip('Date:T', format="%Y-%m-%d"),
                alt.Tooltip('Rebalance Action:N'),
                alt.Tooltip('Unit Change:Q', format='.4f'),
                alt.Tooltip('Units Held:Q', format='.4f'),
                alt.Tooltip('Leveraged Equity:Q', format=',.2f')
            ]
        )
        
        sell_points = alt.Chart(action_data.query("`Rebalance Action` == 'Sell'")).mark_point(
            shape='triangle-down', 
            size=80, 
            color='red',
            filled=True
        ).encode(
            x=alt.X('Date:T'),
            y=alt.Y('Leveraged Equity:Q'),
            tooltip=[
                alt.Tooltip('Date:T', format="%Y-%m-%d"),
                alt.Tooltip('Rebalance Action:N'),
                alt.Tooltip('Unit Change:Q', format='.4f'),
                alt.Tooltip('Units Held:Q', format='.4f'),
                alt.Tooltip('Leveraged Equity:Q', format=',.2f')
            ]
        )

        final_chart = alt.layer(line_chart, buy_points, sell_points).resolve_scale(
            y='shared'
        )

        st.subheader("Strategy Equity Comparison")
        st.markdown(
            "This chart compares the **Leveraged Strategy** against the **Benchmark (Simple Buy & Hold)**. "
            "**Hover** over the lines to see daily stats. The **Green (▲)** and **Red (▼)** "
            "triangles show the exact rebalancing 'Buy' and 'Sell' actions."
        )
        st.altair_chart(final_chart, width='stretch')

    @staticmethod
    def render_risk_analysis_chart(results_df: pd.DataFrame):
        st.subheader("Leveraged Strategy: Risk Analysis")
        st.markdown(
            "This is the **most important chart for risk analysis** of the leveraged "
            "strategy. The blue line is your account's equity. The red line is the "
            "'Liquidation Trigger Level'—the equity value at which your broker "
            "would forcibly close your position. **If the blue line ever touches "
            "the red line, the simulation ends.**"
        )
        st.line_chart(
            results_df[['Leveraged Equity', 'Liquidation Trigger Level']],
            color=["#0000FF", "#FF0000"]
        )

    @staticmethod
    def render_additional_charts(results_df: pd.DataFrame, price_data: pd.DataFrame):
        col_asset, col_cost = st.columns(2)
        
        with col_asset:
            st.subheader(f"{ASSET_TICKER} Close Price")
            st.markdown("The underlying asset's price, for comparison.")
            st.line_chart(price_data['Close'])
        
        with col_cost:
            st.subheader("Leveraged Strategy: Cumulative Costs")
            st.markdown("This chart shows the 'slow bleed' from daily holding costs (swap fees). Notice how it steadily decreases, constantly draining your equity buffer.")
            st.line_chart(results_df['Cumulative Cost'])

    @staticmethod
    def render_raw_data(results_df: pd.DataFrame, price_data: pd.DataFrame):
        with st.expander("Show Raw Simulation Data (first 1000 rows)"):
            st.markdown(
                "The raw daily numbers from the simulation, including your equity, "
                "P&L, costs, liquidation level, units held, and rebalancing actions for that day."
            )
            st.dataframe(results_df.head(1000))
            
        with st.expander("Show Raw Price Data (first 1000 rows)"):
            st.markdown(
                "The raw Open, High, Low, Close (OHLC) data from Yahoo Finance "
                "used for the simulation."
            )
            st.dataframe(price_data.head(1000))
