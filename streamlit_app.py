"""
Leveraged Survival Strategy Backtester

A Streamlit application to backtest the "Leveraged Survival Strategy"
using real S&P 500 historical data from yfinance.

This version includes detailed embedded explanations for all parameters
and charts to make the tool self-explanatory.

v3: Adds a "Simple Buy and Hold" benchmark comparison.
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import logging
from datetime import date
import altair as alt

# --- Setup Basic Logging ---
# This will print to your console
logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] [LOG] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- Hardcoded Broker & Market Assumptions ---
ASSET_TICKER = "^GSPC"
COST_OF_CARRY_DECIMAL = 0.0533 # 5.33% Annual Net Cost
MARGIN_REQ_DECIMAL = 0.05      # 5% Margin (1:20 Leverage)
MARGIN_CLOSEOUT_DECIMAL = 0.50 # 50% Margin Closeout Rule

# --- Helper Functions ---

@st.cache_data
def get_data(ticker, start, end):
    """Fetches historical OHLC data from yfinance."""
    logging.info(f"Fetching data for {ticker} from {start} to {end}")
    
    df = yf.download(ticker, start=start, end=end, auto_adjust=False)
    
    if df.empty:
        st.error("No data found for the given ticker and date range.")
        logging.warning("No data found from yfinance.")
        return None
        
    logging.info(f"Original columns from yfinance: {df.columns}")

    # FIX: If columns are a MultiIndex (e.g., [('Open', '^GSPC'), ...]), flatten them.
    if isinstance(df.columns, pd.MultiIndex):
        logging.info("DataFrame has MultiIndex columns. Flattening...")
        df.columns = df.columns.droplevel(1) # Drops the ticker level
        logging.info(f"New flattened columns: {df.columns}")
        
    df = df[['Open', 'High', 'Low', 'Close']]
    df = df.dropna() # Ensure no NaNs from missing days
    logging.info(f"Data fetched, flattened, and cleaned. Shape: {df.shape}")
    return df

def calculate_target_units(equity, current_price, max_market_drop_percent):
    """
    Calculates the max units based on the strategy formula, given a
    current equity and price.
    This is a pure function that returns the unit count.
    """
    # This function is now generalized for rebalancing
    # We always assume Time Horizon = 0 for the buffer calculation.
    logging.info("--- Inside calculate_target_units ---")
    logging.info(f"  Inputs: E=${equity}, S=${current_price}, MD={max_market_drop_percent}%")

    md_decimal = max_market_drop_percent / 100.0
    broker_buffer_decimal = MARGIN_REQ_DECIMAL * MARGIN_CLOSEOUT_DECIMAL
    cost_buffer_decimal = 0.0 # Per your request, we ignore fees in the buffer

    logging.info(f"  Buffers (decimal): MD={md_decimal:.4f}, "
                 f"Broker={broker_buffer_decimal:.4f}, Cost={cost_buffer_decimal:.4f}")

    total_buffer_decimal = md_decimal + broker_buffer_decimal + cost_buffer_decimal
    logging.info(f"  Total Buffer (decimal): {total_buffer_decimal:.4f}")

    if total_buffer_decimal <= 0:
        logging.error("Total buffer decimal is <= 0. Returning 0 units.")
        return 0.0

    # This is the total capital required to "support" one unit
    total_cost_and_buffer_per_unit = current_price * total_buffer_decimal
    logging.info(f"  Total Cost/Buffer per Unit ($): {total_cost_and_buffer_per_unit:.4f} "
                 f"({current_price} * {total_buffer_decimal})")

    if total_cost_and_buffer_per_unit <= 0:
        logging.error("Total cost/buffer per unit is <= 0. Returning 0 units.")
        return 0.0
        
    # N = Equity / (Total $ support required per unit)
    target_units = equity / total_cost_and_buffer_per_unit
    logging.info(f"  Final Target Units: {target_units:.4f} ({equity} / {total_cost_and_buffer_per_unit})")
    logging.info("--- Exiting calculate_target_units ---")
    return target_units

# --- NEW: DOMAIN LOGIC CLASS ---
# This class follows the Single Responsibility Principle.
# It holds the *state* of the simulation and all the *logic*
# for how that state changes. This also fixes the P&L bug.

class LeveragedAccount:
    """
    Manages the state and logic of the leveraged strategy.
    This fixes the rebalancing P&L bug by tracking equity
    based on daily market-to-market changes.
    """
    def __init__(self, capital, initial_units):
        self.equity = capital
        self.units = initial_units
        self.initial_capital = capital
        self.cumulative_cost = 0.0
        self.liquidated = False
        self.liquidation_date = None
        
        # We need to track the previous day's close to calculate
        # the P&L from price *changes*.
        self.previous_day_close = 0.0
        
        # --- NEW: State for periodic rebalancing ---
        self.previous_month = None
        self.previous_quarter = None

    def apply_daily_tick(self, date, row, params):
        """
        Applies all logic for a single day of the simulation.
        """
        if self.liquidated:
            return

        # --- 1. Check for Liquidation (based on Daily Low) ---
        pnl_at_low = (row['Low'] - self.previous_day_close) * self.units
        equity_at_low = self.equity + pnl_at_low
        
        required_margin = (row['Low'] * self.units) * params['margin_req']
        liquidation_trigger = required_margin * params['margin_closeout']

        if equity_at_low <= liquidation_trigger:
            self.liquidated = True
            self.liquidation_date = date
            # Final equity is the "wipeout" value
            self.equity = liquidation_trigger
            logging.warning(f"  LIQUIDATION on {date}!")
            logging.warning(f"    Equity at Low ({equity_at_low:.2f}) <= "
                            f"Trigger ({liquidation_trigger:.2f})")
            return

        # --- 2. Calculate P&L and Costs (based on Daily Close) ---
        price_change = row['Close'] - self.previous_day_close
        market_pnl = self.units * price_change
        
        position_value_at_close = row['Close'] * self.units
        daily_cost = position_value_at_close * params['daily_coc']
        
        # This is the correct equity calculation!
        self.equity += market_pnl - daily_cost
        self.cumulative_cost -= daily_cost # Costs are a negative value

        # --- 3. Rebalance (if enabled) ---
        if self._should_rebalance(date, params['rebalance_frequency']):
            self.rebalance(row['Close'], params)

        # Finally, set the close price for the next day's calculation
        self.previous_day_close = row['Close']

    def _should_rebalance(self, date, frequency):
        """Helper to check if today is a rebalance day."""
        if frequency == "Never":
            return False
        
        if frequency == "Daily":
            return True

        perform_rebalance_today = False

        if frequency == "Monthly":
            current_month = date.month
            if self.previous_month is None: # First day of simulation
                self.previous_month = current_month
            
            if current_month != self.previous_month:
                perform_rebalance_today = True
            
            self.previous_month = current_month # Update for next day
        
        elif frequency == "Quarterly":
            current_quarter = (date.month - 1) // 3 + 1
            if self.previous_quarter is None: # First day
                self.previous_quarter = current_quarter
            
            if current_quarter != self.previous_quarter:
                perform_rebalance_today = True
            
            self.previous_quarter = current_quarter # Update for next day
        
        return perform_rebalance_today

    def rebalance(self, close_price, params):
        """
        Adjusts unit count to match the target risk.
        This no longer has the P&L bug.
        """
        target_units = calculate_target_units(
            self.equity, 
            close_price, 
            params['max_drop_percent']
        )
        self.units = target_units # Just set the new target

def run_simulation(capital, initial_units, entry_price, historical_data, rebalance_frequency, max_drop_percent):
    """
    Runs the day-by-day backtest simulation (REFACTORED).
    This function now delegates all logic to the LeveragedAccount class.
    """
    logging.info("--- Inside run_simulation (Refactored) ---")
    
    # Pack all our assumptions into a 'params' dict for easy passing
    sim_params = {
        "margin_req": MARGIN_REQ_DECIMAL,
        "margin_closeout": MARGIN_CLOSEOUT_DECIMAL,
        "daily_coc": COST_OF_CARRY_DECIMAL / 365.0,
        "rebalance_frequency": rebalance_frequency,  # Pass the actual frequency string
        "max_drop_percent": max_drop_percent
    }
    
    # --- 1. Setup the Account ---
    account = LeveragedAccount(capital, initial_units)
    # IMPORTANT: Set the "starting" price for the P&L calculation
    account.previous_day_close = entry_price 

    # --- 2. Setup Data Recording ---
    # We create lists to store the results from the account
    dates = []
    equity_values = []
    unit_values = []
    cost_values = []
    action_values = []
    trigger_values = []
    unit_change_values = []  # Track unit changes to avoid .diff() misalignment

    logging.info(f"Starting simulation loop for {len(historical_data)} days...")
    
    for date, row in historical_data.iterrows():
        # --- 3. Run the Daily Tick ---
        # Get the unit count *before* the tick
        units_before = account.units
        account.apply_daily_tick(date, row, sim_params)
        
        # --- 4. Record the Results ---
        dates.append(date)
        equity_values.append(account.equity)
        cost_values.append(account.cumulative_cost)
        unit_values.append(account.units)
        
        # Calculate daily action
        unit_change = account.units - units_before
        if unit_change > 0.01:
            action = "Buy"
        elif unit_change < -0.01:
            action = "Sell"
        else: 
            action = "Hold"
            unit_change = 0.0  # Explicitly set to 0 to avoid floating-point noise
        
        action_values.append(action)
        unit_change_values.append(unit_change)  # Save the value for DataFrame

        # Calculate the liquidation trigger for the chart
        req_margin = (row['Close'] * account.units) * sim_params['margin_req']
        trigger = req_margin * sim_params['margin_closeout']
        trigger_values.append(trigger)
        
        if account.liquidated:
            break # Stop the loop if liquidated

    # --- 5. Format the Results ---
    logging.info(f"Simulation loop finished. Liquidated: {account.liquidated}")
        
    results_df = pd.DataFrame(
        {
            'Leveraged Equity': equity_values,
            'Cumulative Cost': cost_values,
            'Liquidation Trigger Level': trigger_values,
            'Units Held': unit_values,
            'Unit Change': unit_change_values,  # Use the clean list (no .diff())
            'Rebalance Action': action_values
        },
        index=pd.to_datetime(dates)
    )
    
    summary = {
        "liquidated": account.liquidated,
        "liquidation_date": account.liquidation_date,
        "final_equity": account.equity,
        "total_return_pct": ((account.equity / capital) - 1) * 100,
        "total_costs_paid": -account.cumulative_cost,
        "initial_units": initial_units
    }
    
    logging.info("--- Exiting run_simulation (Refactored) ---")
    return results_df, summary

def run_benchmark_simulation(capital, entry_price, historical_data):
    """
    Runs a simple, unleveraged "buy and hold" simulation.
    No fees, no margin calls.
    """
    logging.info("--- Inside run_benchmark_simulation ---")
    benchmark_units = capital / entry_price
    logging.info(f"  Benchmark Units: {benchmark_units:.4f} ({capital} / {entry_price})")
    
    # Calculate equity based on the closing price of each day (vectorized)
    benchmark_equity = benchmark_units * historical_data['Close']
    
    results_df = pd.DataFrame({'Equity': benchmark_equity})
    
    # Calculate final summary
    final_benchmark_equity = 0.0
    total_benchmark_return = 0.0
    
    if not results_df.empty:
        final_benchmark_equity = results_df['Equity'].iloc[-1]
        total_benchmark_return = ((final_benchmark_equity / capital) - 1) * 100
    
    summary = {
        "final_equity": final_benchmark_equity,
        "total_return_pct": total_benchmark_return,
        "units_held": benchmark_units
    }
    logging.info("--- Exiting run_benchmark_simulation ---")
    return results_df, summary

# --- Streamlit App UI ---

st.set_page_config(layout="wide")
st.title("📈 Leveraged Survival Strategy Backtester")
st.markdown(f"""
    This app backtests the **"Leveraged Survival Strategy"** against a 
    **"Simple Buy & Hold"** benchmark.
    Both strategies are tested on **{ASSET_TICKER}**.
""")

# --- NEW: Embedded Explanations ---
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
        
        ---
        
        ### An Example Calculation
        
        How are `Initial Units` calculated? Let's use the defaults:
        * **Capital ($C$):** $10,000
        * **Max Drop ($MD$):** 30% (or 0.30)
        * **Time Horizon ($T$):** 1.0 Year
        
        **Leveraged Strategy Calculation:**
        * **Total Buffer** = `Market Drop (30%)` + `Broker (2.5%)` + `Costs (0% - ignored)`
        * **Total Buffer** = `0.30 + 0.025 + 0.0 = 0.325` (32.5%)
        * *Assuming $1,116 entry price:*
        * **$ Buffer per Unit** = `$1,116 * 0.325 = $362.70`
        * **Max Units** = `$10,000 / $362.70 =` **27.57 Units**
        
        **Benchmark Strategy Calculation:**
        * *Assuming $1,116 entry price:*
        * **Max Units** = `$10,000 / $1,116 =` **8.96 Units**
        """
    )

# --- 1. Sidebar Inputs ---
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

# NEW: Rebalancing Frequency Dropdown
rebalance_frequency = st.sidebar.selectbox(
    "Rebalancing Frequency",
    options=["Never", "Daily", "Monthly", "Quarterly"],
    index=0, # Default to "Never"
    help=(
        "How often to rebalance your position to the risk target. "
        "'Never' is a static 'buy and hold' of the initial units. "
        "'Daily' is the most aggressive (and riskiest). "
        "'Monthly' or 'Quarterly' are common alternatives."
    )
)

st.sidebar.header("Backtest Period")
# Explicitly set a wide allowed date range to override strange defaults
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
    max_allowed_date, # Default to today
    min_value=min_allowed_date,
    max_value=max_allowed_date
)

if st.sidebar.button("Run Backtest", type="primary"):
    logging.info("--- 'Run Backtest' button clicked ---")
    
    # --- 2. Data Fetching & Initial Calculation ---
    with st.spinner(f"Fetching {ASSET_TICKER} data..."):
        data = get_data(ASSET_TICKER, start_date, end_date)
    
    if data is not None and not data.empty:
        # Robustly select the first 'Open' price from the first row.
        entry_price_raw = data.iloc[0]['Open']
        
        # Ensure entry_price is a scalar float
        if isinstance(entry_price_raw, pd.Series):
            entry_price = entry_price_raw.iloc[0]
            logging.warning(f"Entry price was a Series, selected first val: {entry_price}")
        else:
            entry_price = entry_price_raw
        
        logging.info(f"Entry Price selected: {entry_price} (Type: {type(entry_price)})")

        # We now call the renamed function 'calculate_target_units'
        initial_units = calculate_target_units(
            capital_input, 
            entry_price, 
            max_drop_input
        )
        
        logging.info(f"Initial units calculated: {initial_units}")
        st.header("Backtest Results")
        
        # --- 3. Simulation ---
        with st.spinner("Running leveraged simulation..."):
            results_df, summary = run_simulation(
                capital_input, 
                initial_units, 
                entry_price, 
                data,
                rebalance_frequency=rebalance_frequency, # Pass the frequency string
                max_drop_percent=max_drop_input 
            )
        
        with st.spinner("Running benchmark simulation..."):
            benchmark_df, benchmark_summary = run_benchmark_simulation(
                capital_input,
                entry_price,
                data 
            )
        
        logging.info("Simulations complete. Displaying results.")
        
        # --- 4. Display KPIs ---
        # Merge benchmark equity into results
        results_df['Benchmark Equity'] = benchmark_df['Equity']

        
        if summary['liquidated']:
            st.error(f"❌ **LEVERAGED STRATEGY LIQUIDATED** on {summary['liquidation_date'].strftime('%Y-%m-%d')}")
        else:
            st.success("✅ **LEVERAGED STRATEGY SURVIVED** - Position was not liquidated.")
            
        st.subheader("Strategy Performance Summary")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Leveraged Survival Strategy")
            c1, c2 = st.columns(2)
            c1.metric("Initial Units", f"{summary['initial_units']:.4f}")
            c2.metric("Total Costs Paid", f"${summary['total_costs_paid']:,.2f}")
            c1.metric("Final Equity", f"${summary['final_equity']:,.2f}")
            c2.metric("Total Return", f"{summary['total_return_pct']:,.2f}%")

        with col2:
            st.markdown("#### Simple Buy & Hold (Benchmark)")
            c3, c4 = st.columns(2)
            c3.metric("Initial Units", f"{benchmark_summary['units_held']:.4f}")
            c4.metric("Total Costs Paid", "$0.00")
            c3.metric("Final Equity", f"${benchmark_summary['final_equity']:,.2f}")
            c4.metric("Total Return", f"{benchmark_summary['total_return_pct']:,.2f}%")


        # --- 5. Display Charts (with descriptions) ---
        
        # --- NEW: Build the Interactive Altair Chart ---
        
        # Step 1: Prepare the data
        # Altair prefers "long-form" data for plotting lines with legends
        # We also reset the index to get 'Date' as a proper column
        chart_data_long = results_df.reset_index().rename(
            columns={'index': 'Date'}
        ).melt(
            id_vars=['Date', 'Units Held', 'Unit Change', 'Rebalance Action'], 
            value_vars=['Leveraged Equity', 'Benchmark Equity'],
            var_name='Strategy', 
            value_name='Equity'
        )
        
        # Step 2: Create a base chart
        base = alt.Chart(chart_data_long).encode(
            x=alt.X('Date:T', axis=alt.Axis(title='Date', format="%Y-%m-%d")),
        ).interactive()

        # Step 3: Create the line layers
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

        # Step 4: Create the rebalancing action markers (Buy/Sell)
        # We only want to plot points where an action occurred
        action_data = results_df.reset_index().rename(
            columns={'index': 'Date'}
        ).query("`Rebalance Action` != 'Hold'")

        # Create green 'Buy' triangles
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
        
        # Create red 'Sell' triangles
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

        # Step 5: Combine the layers
        final_chart = alt.layer(line_chart, buy_points, sell_points).resolve_scale(
            y='shared'
        )

        # Display the new chart
        st.subheader("Strategy Equity Comparison")
        st.markdown(
            "This chart compares the **Leveraged Strategy** against the **Benchmark (Simple Buy & Hold)**. "
            "**Hover** over the lines to see daily stats. The **Green (▲)** and **Red (▼)** "
            "triangles show the exact rebalancing 'Buy' and 'Sell' actions."
        )
        st.altair_chart(final_chart, width='stretch')
        
        
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
            color=["#0000FF", "#FF0000"] # Blue for Equity, Red for Trigger
        )

        col_asset, col_cost = st.columns(2)
        
        with col_asset:
            st.subheader(f"{ASSET_TICKER} Close Price")
            st.markdown("The underlying asset's price, for comparison.")
            st.line_chart(data['Close'])
        
        with col_cost:
            st.subheader("Leveraged Strategy: Cumulative Costs")
            st.markdown("This chart shows the 'slow bleed' from daily holding costs (swap fees). Notice how it steadily decreases, constantly draining your equity buffer.")
            st.line_chart(results_df['Cumulative Cost'])

        # --- 6. Display Raw Data (with descriptions) ---
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
            st.dataframe(data.head(1000))

    else:
        st.error("Failed to fetch data. Cannot run simulation.")
        logging.error("Data was None or empty, skipping simulation.")

else:
    st.info("Click 'Run Backtest' in the sidebar to start the simulation.")
