"""
Unit tests for the Leveraged Survival Strategy backtester.

This test suite verifies:
1. Target units calculation
2. Daily tick processing
3. Liquidation logic
4. Rebalancing logic
5. Mark-to-market P&L (phantom profit bug fix)

Run with: pytest test_leveraged_account.py -v
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import the functions and classes we're testing
# Note: In actual implementation, these would be in separate modules
import sys
import importlib.util

# Load the streamlit_app module
spec = importlib.util.spec_from_file_location("streamlit_app", "streamlit_app.py")
streamlit_app = importlib.util.module_from_spec(spec)

# Mock streamlit before loading
class MockStreamlit:
    @staticmethod
    def cache_data(func):
        return func
    
    def error(self, msg): pass
    def warning(self, msg): pass
    def info(self, msg): pass
    def set_page_config(self, **kwargs): pass
    def title(self, text): pass
    def markdown(self, text): pass
    def expander(self, label, expanded=False): 
        class MockExpander:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def markdown(self, text): pass
        return MockExpander()
    
    class sidebar:
        @staticmethod
        def header(text): pass
        @staticmethod
        def number_input(*args, **kwargs): return 10000.0
        @staticmethod
        def slider(*args, **kwargs): return 30.0
        @staticmethod
        def selectbox(*args, **kwargs): return "Never"
        @staticmethod
        def date_input(*args, **kwargs): return None
        @staticmethod
        def button(*args, **kwargs): return False

sys.modules['streamlit'] = MockStreamlit()
spec.loader.exec_module(streamlit_app)

# Import what we need
calculate_target_units = streamlit_app.calculate_target_units
LeveragedAccount = streamlit_app.LeveragedAccount

# Constants from the app
MARGIN_REQ_DECIMAL = 0.05
MARGIN_CLOSEOUT_DECIMAL = 0.50
COST_OF_CARRY_DECIMAL = 0.0533


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def basic_params():
    """Basic simulation parameters."""
    return {
        'margin_req': MARGIN_REQ_DECIMAL,
        'margin_closeout': MARGIN_CLOSEOUT_DECIMAL,
        'daily_coc': COST_OF_CARRY_DECIMAL / 365.0,
        'rebalance_frequency': 'Never',
        'max_drop_percent': 30.0
    }


@pytest.fixture
def sample_price_row():
    """Sample price data for one day."""
    return {
        'Open': 1000.0,
        'High': 1020.0,
        'Low': 980.0,
        'Close': 1010.0
    }


@pytest.fixture
def flat_price_row():
    """Flat price (no change) for testing."""
    return {
        'Open': 1000.0,
        'High': 1005.0,
        'Low': 995.0,
        'Close': 1000.0
    }


# ============================================================================
# TEST: TARGET UNITS CALCULATION
# ============================================================================

class TestTargetUnitsCalculation:
    """Tests for calculate_target_units() function."""
    
    def test_basic_calculation(self):
        """Test basic target units calculation with standard inputs."""
        equity = 10000.0
        price = 1000.0
        max_drop = 30.0
        
        # Expected buffer: 0.30 + (0.05 * 0.50) + 0 = 0.325
        # Expected cost per unit: 1000 * 0.325 = 325
        # Expected units: 10000 / 325 = 30.769...
        
        units = calculate_target_units(equity, price, max_drop)
        
        expected_buffer = 0.30 + (0.05 * 0.50)
        expected_units = equity / (price * expected_buffer)
        
        assert abs(units - expected_units) < 0.001
        assert units > 0
    
    def test_different_max_drops(self):
        """Test that higher max_drop results in fewer units."""
        equity = 10000.0
        price = 1000.0
        
        units_10 = calculate_target_units(equity, price, 10.0)
        units_30 = calculate_target_units(equity, price, 30.0)
        units_50 = calculate_target_units(equity, price, 50.0)
        
        # Higher max drop = more conservative = fewer units
        assert units_10 > units_30 > units_50
    
    def test_different_prices(self):
        """Test that higher prices result in fewer units."""
        equity = 10000.0
        max_drop = 30.0
        
        units_1000 = calculate_target_units(equity, 1000.0, max_drop)
        units_2000 = calculate_target_units(equity, 2000.0, max_drop)
        
        # Higher price = fewer units (with same equity)
        assert units_1000 > units_2000
        assert abs(units_1000 / units_2000 - 2.0) < 0.01  # Should be ~2x
    
    def test_different_equity(self):
        """Test that higher equity results in more units."""
        price = 1000.0
        max_drop = 30.0
        
        units_5000 = calculate_target_units(5000.0, price, max_drop)
        units_10000 = calculate_target_units(10000.0, price, max_drop)
        units_20000 = calculate_target_units(20000.0, price, max_drop)
        
        # Higher equity = more units (proportional)
        assert units_5000 < units_10000 < units_20000
        assert abs(units_10000 / units_5000 - 2.0) < 0.01
        assert abs(units_20000 / units_10000 - 2.0) < 0.01
    
    def test_edge_case_small_buffer(self):
        """Test behavior with very small max_drop."""
        equity = 10000.0
        price = 1000.0
        
        # Very small max_drop (0.1%) + broker buffer (2.5%) = 2.6% total
        # This actually allows MORE leverage than unleveraged position
        units = calculate_target_units(equity, price, 0.1)
        assert units > 0
        
        # With such a small buffer, we get high leverage
        # Buffer = 0.001 + 0.025 = 0.026, so units = 10000/(1000*0.026) = 384.6
        expected_units = equity / (price * (0.001 + 0.025))
        assert abs(units - expected_units) < 0.1


# ============================================================================
# TEST: LEVERAGED ACCOUNT INITIALIZATION
# ============================================================================

class TestLeveragedAccountInit:
    """Tests for LeveragedAccount initialization."""
    
    def test_initialization(self):
        """Test account is initialized correctly."""
        capital = 10000.0
        units = 27.5
        
        account = LeveragedAccount(capital, units)
        
        assert account.equity == capital
        assert account.units == units
        assert account.initial_capital == capital
        assert account.cumulative_cost == 0.0
        assert account.liquidated is False
        assert account.liquidation_date is None
        assert account.previous_day_close == 0.0
    
    def test_initialization_different_values(self):
        """Test initialization with various values."""
        test_cases = [
            (5000.0, 10.0),
            (100000.0, 250.5),
            (1000.0, 2.5)
        ]
        
        for capital, units in test_cases:
            account = LeveragedAccount(capital, units)
            assert account.equity == capital
            assert account.units == units


# ============================================================================
# TEST: DAILY TICK PROCESSING (NO REBALANCING)
# ============================================================================

class TestDailyTickProcessing:
    """Tests for apply_daily_tick() without rebalancing."""
    
    def test_flat_market_no_pnl(self, basic_params, flat_price_row):
        """Test that flat market (no price change) results in no P&L."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        initial_equity = account.equity
        
        # Apply tick with flat prices
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            flat_price_row,
            basic_params
        )
        
        # Calculate expected cost
        position_value = flat_price_row['Close'] * account.units
        expected_cost = position_value * basic_params['daily_coc']
        
        # Equity should decrease by cost only (no P&L)
        expected_equity = initial_equity - expected_cost
        
        assert abs(account.equity - expected_equity) < 0.01
        assert not account.liquidated
    
    def test_up_market_positive_pnl(self, basic_params, sample_price_row):
        """Test that rising market results in positive P&L."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        initial_equity = account.equity
        
        # Apply tick (price goes from 1000 to 1010)
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            sample_price_row,
            basic_params
        )
        
        # Calculate expected P&L and cost
        price_change = sample_price_row['Close'] - 1000.0  # +10
        market_pnl = account.units * price_change  # 27.5 * 10 = 275
        
        position_value = sample_price_row['Close'] * account.units
        cost = position_value * basic_params['daily_coc']
        
        expected_equity = initial_equity + market_pnl - cost
        
        assert abs(account.equity - expected_equity) < 0.01
        assert account.equity > initial_equity  # Net positive
        assert not account.liquidated
    
    def test_down_market_negative_pnl(self, basic_params):
        """Test that falling market results in negative P&L."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        initial_equity = account.equity
        
        # Price drops from 1000 to 990
        down_row = {
            'Open': 1000.0,
            'High': 1000.0,
            'Low': 985.0,
            'Close': 990.0
        }
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            down_row,
            basic_params
        )
        
        # Calculate expected P&L and cost
        price_change = 990.0 - 1000.0  # -10
        market_pnl = account.units * price_change  # 27.5 * (-10) = -275
        
        position_value = 990.0 * account.units
        cost = position_value * basic_params['daily_coc']
        
        expected_equity = initial_equity + market_pnl - cost
        
        assert abs(account.equity - expected_equity) < 0.01
        assert account.equity < initial_equity  # Net negative
        assert not account.liquidated
    
    def test_cumulative_cost_tracking(self, basic_params, sample_price_row):
        """Test that cumulative costs are tracked correctly."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Apply multiple days
        for i in range(5):
            account.apply_daily_tick(
                datetime(2024, 1, 1) + timedelta(days=i),
                sample_price_row,
                basic_params
            )
        
        # Cumulative cost should be negative (it's a cost)
        assert account.cumulative_cost < 0
        
        # Cost should be significant over 5 days
        assert abs(account.cumulative_cost) > 0
    
    def test_previous_close_updates(self, basic_params, sample_price_row):
        """Test that previous_day_close is updated correctly."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            sample_price_row,
            basic_params
        )
        
        # Previous close should now be updated to today's close
        assert account.previous_day_close == sample_price_row['Close']


# ============================================================================
# TEST: LIQUIDATION LOGIC
# ============================================================================

class TestLiquidationLogic:
    """Tests for liquidation detection and handling."""
    
    def test_no_liquidation_safe_position(self, basic_params):
        """Test that safe positions don't get liquidated."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Small price drop
        safe_row = {
            'Open': 1000.0,
            'High': 1010.0,
            'Low': 990.0,  # 1% drop
            'Close': 995.0
        }
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            safe_row,
            basic_params
        )
        
        assert not account.liquidated
        assert account.liquidation_date is None
    
    def test_liquidation_on_large_drop(self, basic_params):
        """Test that large price drop triggers liquidation."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Large price drop (35% - exceeds 30% buffer + 2.5% margin buffer)
        crash_row = {
            'Open': 1000.0,
            'High': 1000.0,
            'Low': 650.0,  # 35% drop
            'Close': 660.0
        }
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            crash_row,
            basic_params
        )
        
        assert account.liquidated
        assert account.liquidation_date == datetime(2024, 1, 1)
    
    def test_liquidation_sets_equity_to_trigger(self, basic_params):
        """Test that equity is set to trigger level on liquidation."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        crash_row = {
            'Open': 1000.0,
            'High': 1000.0,
            'Low': 650.0,
            'Close': 660.0
        }
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            crash_row,
            basic_params
        )
        
        # Calculate what trigger should be
        required_margin = crash_row['Low'] * account.units * basic_params['margin_req']
        expected_trigger = required_margin * basic_params['margin_closeout']
        
        assert abs(account.equity - expected_trigger) < 0.01
    
    def test_no_updates_after_liquidation(self, basic_params, sample_price_row):
        """Test that account doesn't update after liquidation."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # First, cause liquidation
        crash_row = {
            'Open': 1000.0,
            'High': 1000.0,
            'Low': 650.0,
            'Close': 660.0
        }
        
        account.apply_daily_tick(datetime(2024, 1, 1), crash_row, basic_params)
        
        liquidation_equity = account.equity
        
        # Try to apply another tick (should do nothing)
        account.apply_daily_tick(datetime(2024, 1, 2), sample_price_row, basic_params)
        
        # Equity should not change
        assert account.equity == liquidation_equity
        assert account.liquidated


# ============================================================================
# TEST: REBALANCING LOGIC
# ============================================================================

class TestRebalancingLogic:
    """Tests for rebalancing functionality."""
    
    def test_daily_rebalancing_enabled(self, basic_params, sample_price_row):
        """Test that daily rebalancing works when enabled."""
        rebalance_params = basic_params.copy()
        rebalance_params['rebalance_frequency'] = 'Daily'
        
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        initial_units = account.units
        
        # Price goes up, equity increases, should rebalance to more units
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            sample_price_row,
            rebalance_params
        )
        
        # Units should have changed (increased because equity increased)
        assert account.units != initial_units
        assert account.units > initial_units
    
    def test_no_rebalancing_when_disabled(self, basic_params, sample_price_row):
        """Test that rebalancing doesn't happen when disabled."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        initial_units = account.units
        
        # Apply tick with rebalancing disabled (default in basic_params)
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            sample_price_row,
            basic_params
        )
        
        # Units should NOT have changed
        assert account.units == initial_units
    
    def test_rebalancing_increases_units_on_gains(self, basic_params):
        """Test that units increase when equity increases."""
        rebalance_params = basic_params.copy()
        rebalance_params['rebalance_frequency'] = 'Daily'
        
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        initial_units = account.units
        
        # Large price increase
        up_row = {
            'Open': 1000.0,
            'High': 1100.0,
            'Low': 1000.0,
            'Close': 1100.0  # +10% gain
        }
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            up_row,
            rebalance_params
        )
        
        # Units should have increased (equity increased, can buy more)
        assert account.units > initial_units
    
    def test_rebalancing_decreases_units_on_losses(self, basic_params):
        """Test that units decrease when equity decreases."""
        rebalance_params = basic_params.copy()
        rebalance_params['rebalance_frequency'] = 'Daily'
        
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        initial_units = account.units
        
        # Price decrease (but not enough to liquidate)
        down_row = {
            'Open': 1000.0,
            'High': 1000.0,
            'Low': 900.0,
            'Close': 900.0  # -10% loss
        }
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            down_row,
            rebalance_params
        )
        
        # Units should have decreased (equity decreased, must reduce exposure)
        assert account.units < initial_units


# ============================================================================
# TEST: PHANTOM PROFIT BUG FIX (CRITICAL TEST)
# ============================================================================

class TestPhantomProfitBugFix:
    """Tests verifying the phantom profit bug is fixed."""
    
    def test_no_phantom_profits_on_rebalance(self, basic_params):
        """
        CRITICAL TEST: Verify no phantom profits when rebalancing adds units.
        
        This test specifically checks the bug fix:
        - Old code: Applied full historical profit to new units
        - New code: Correctly uses mark-to-market accounting
        """
        rebalance_params = basic_params.copy()
        rebalance_params['rebalance_frequency'] = 'Daily'
        
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Day 1: Price goes up significantly
        up_row = {
            'Open': 1000.0,
            'High': 1500.0,
            'Low': 1000.0,
            'Close': 1500.0  # +50% gain
        }
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            up_row,
            rebalance_params
        )
        
        equity_after_day1 = account.equity
        units_after_day1 = account.units
        
        # Day 2: Price stays flat (no change)
        flat_row = {
            'Open': 1500.0,
            'High': 1505.0,
            'Low': 1495.0,
            'Close': 1500.0  # NO CHANGE
        }
        
        account.apply_daily_tick(
            datetime(2024, 1, 2),
            flat_row,
            rebalance_params
        )
        
        # Calculate expected equity change
        # Price didn't change, so P&L should be ~0 (minus costs)
        expected_cost = 1500.0 * units_after_day1 * rebalance_params['daily_coc']
        expected_equity = equity_after_day1 - expected_cost
        
        # With the bug, equity would have jumped significantly
        # With the fix, equity should only decrease by cost
        assert abs(account.equity - expected_equity) < 1.0
        
        # Verify no huge unexpected jump
        equity_change = account.equity - equity_after_day1
        assert equity_change < 0  # Should be negative (cost)
        assert abs(equity_change) < 100  # Should be small (just cost, not phantom profit)
    
    def test_mark_to_market_correctness(self, basic_params):
        """Test that mark-to-market P&L is calculated correctly across multiple days."""
        rebalance_params = basic_params.copy()
        rebalance_params['rebalance_frequency'] = 'Daily'
        
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Track equity changes manually
        equity_history = [account.equity]
        
        # Day 1: +5%
        day1_row = {'Open': 1000.0, 'High': 1050.0, 'Low': 1000.0, 'Close': 1050.0}
        account.apply_daily_tick(datetime(2024, 1, 1), day1_row, rebalance_params)
        equity_history.append(account.equity)
        
        # Day 2: -3%
        day2_row = {'Open': 1050.0, 'High': 1050.0, 'Low': 1010.0, 'Close': 1018.5}
        account.apply_daily_tick(datetime(2024, 1, 2), day2_row, rebalance_params)
        equity_history.append(account.equity)
        
        # Day 3: +2%
        day3_row = {'Open': 1018.5, 'High': 1040.0, 'Low': 1018.5, 'Close': 1038.87}
        account.apply_daily_tick(datetime(2024, 1, 3), day3_row, rebalance_params)
        equity_history.append(account.equity)
        
        # Each day should have reasonable changes (no huge jumps)
        for i in range(1, len(equity_history)):
            change_pct = (equity_history[i] - equity_history[i-1]) / equity_history[i-1]
            assert abs(change_pct) < 0.20  # No single day change > 20%
    
    def test_rebalancing_after_units_increase(self, basic_params):
        """
        Test that after rebalancing increases units, the next day's P&L
        is calculated correctly based on NEW unit count.
        """
        rebalance_params = basic_params.copy()
        rebalance_params['rebalance_frequency'] = 'Daily'
        
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Day 1: Big gain, units will increase
        day1_row = {'Open': 1000.0, 'High': 1200.0, 'Low': 1000.0, 'Close': 1200.0}
        account.apply_daily_tick(datetime(2024, 1, 1), day1_row, rebalance_params)
        
        units_after_rebalance = account.units
        equity_after_rebalance = account.equity
        
        # Day 2: 1% gain
        day2_row = {'Open': 1200.0, 'High': 1212.0, 'Low': 1200.0, 'Close': 1212.0}
        account.apply_daily_tick(datetime(2024, 1, 2), day2_row, rebalance_params)
        
        # Calculate expected P&L based on NEW unit count
        price_change = 1212.0 - 1200.0  # +12
        expected_pnl = units_after_rebalance * price_change
        expected_cost = 1212.0 * units_after_rebalance * rebalance_params['daily_coc']
        expected_equity = equity_after_rebalance + expected_pnl - expected_cost
        
        assert abs(account.equity - expected_equity) < 0.1


# ============================================================================
# TEST: INTEGRATION SCENARIOS
# ============================================================================

class TestIntegrationScenarios:
    """Integration tests with realistic market scenarios."""
    
    def test_bull_market_scenario(self, basic_params):
        """Test account behavior in a sustained bull market."""
        rebalance_params = basic_params.copy()
        rebalance_params['rebalance_frequency'] = 'Daily'
        
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Simulate 10 days of steady gains (1% per day)
        price = 1000.0
        for i in range(10):
            price *= 1.01  # +1% each day
            row = {
                'Open': price * 0.99,
                'High': price * 1.01,
                'Low': price * 0.99,
                'Close': price
            }
            account.apply_daily_tick(
                datetime(2024, 1, 1) + timedelta(days=i),
                row,
                rebalance_params
            )
        
        # After 10 days of 1% gains, equity should have increased
        assert account.equity > 10000.0
        assert not account.liquidated
    
    def test_volatile_market_scenario(self, basic_params):
        """Test account behavior in a volatile but flat market."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Simulate 5 days of volatility but ending at same price
        prices = [1050.0, 950.0, 1100.0, 900.0, 1000.0]
        
        for i, price in enumerate(prices):
            row = {
                'Open': account.previous_day_close,
                'High': price * 1.02,
                'Low': price * 0.98,
                'Close': price
            }
            account.apply_daily_tick(
                datetime(2024, 1, 1) + timedelta(days=i),
                row,
                basic_params
            )
        
        # Price ended where it started, but costs accumulated
        assert account.equity < 10000.0  # Should be down by costs
        assert not account.liquidated
    
    def test_crash_recovery_scenario(self, basic_params):
        """Test account survives a crash within tolerance and recovers."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Day 1: Crash 25% (within 30% tolerance)
        crash_row = {
            'Open': 1000.0,
            'High': 1000.0,
            'Low': 750.0,
            'Close': 750.0
        }
        account.apply_daily_tick(datetime(2024, 1, 1), crash_row, basic_params)
        
        assert not account.liquidated  # Should survive 25% drop
        
        # Day 2-5: Recovery
        prices = [800.0, 850.0, 900.0, 950.0]
        for i, price in enumerate(prices):
            row = {
                'Open': account.previous_day_close,
                'High': price * 1.02,
                'Low': price * 0.98,
                'Close': price
            }
            account.apply_daily_tick(
                datetime(2024, 1, 2) + timedelta(days=i),
                row,
                basic_params
            )
        
        assert not account.liquidated
        # Equity should have recovered somewhat
        assert account.equity > 6000.0  # Lost less than 40%


# ============================================================================
# TEST: EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_very_small_units(self, basic_params, sample_price_row):
        """Test account with very small number of units."""
        account = LeveragedAccount(1000.0, 0.5)
        account.previous_day_close = 1000.0
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            sample_price_row,
            basic_params
        )
        
        assert not account.liquidated
        assert account.equity > 0
    
    def test_large_position(self, basic_params, sample_price_row):
        """Test account with large position."""
        account = LeveragedAccount(1000000.0, 2750.0)
        account.previous_day_close = 1000.0
        
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            sample_price_row,
            basic_params
        )
        
        assert not account.liquidated
        assert account.equity > 0
    
    def test_extreme_volatility(self, basic_params):
        """Test with extreme intraday volatility."""
        account = LeveragedAccount(10000.0, 27.5)
        account.previous_day_close = 1000.0
        
        # Extreme volatility but closes near open
        volatile_row = {
            'Open': 1000.0,
            'High': 1500.0,  # +50%
            'Low': 500.0,    # -50%
            'Close': 1010.0
        }
        
        # Should liquidate due to low exceeding buffer
        account.apply_daily_tick(
            datetime(2024, 1, 1),
            volatile_row,
            basic_params
        )
        
        # The 50% drop to 500 should trigger liquidation
        assert account.liquidated


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
