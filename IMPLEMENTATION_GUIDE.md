# Leveraged Survival Strategy - Implementation Guide

## Overview

This document explains the logic, calculations, and implementation details of the Leveraged Survival Strategy backtester, including the critical bug fix and refactoring applied in the latest version.

## Table of Contents

1. [Strategy Concept](#strategy-concept)
2. [The Critical Bug (Now Fixed)](#the-critical-bug-now-fixed)
3. [Implementation Architecture](#implementation-architecture)
4. [Mathematical Formulas](#mathematical-formulas)
5. [Code Structure](#code-structure)
6. [Testing Strategy](#testing-strategy)

---

## Strategy Concept

### What is the Leveraged Survival Strategy?

The strategy aims to use leverage (1:20 via CFDs or futures) while ensuring survival through a predetermined market crash without liquidation.

**Key Principles:**
- Calculate maximum position size based on a "worst case" market drop
- Account for broker margin requirements (5% = 20x leverage)
- Account for margin closeout level (50% of required margin)
- Track daily holding costs (5.33% annual "cost of carry")
- Optional: Rebalance position to maintain constant risk exposure

### Why This Matters

Traditional leveraged strategies often fail because traders:
1. Over-leverage (too many units)
2. Ignore holding costs
3. Don't plan for worst-case scenarios
4. Get liquidated during normal market volatility

This strategy flips the approach: **Start with the crash you want to survive, then calculate the maximum safe position size.**

---

## The Critical Bug (Now Fixed)

### The Problem

**In versions prior to the refactoring**, the rebalancing feature had a critical P&L calculation bug:

```python
# OLD (BUGGY) CODE:
pnl_at_close = (daily_close_price - entry_price) * current_units
current_equity = capital + pnl_at_close + running_cumulative_cost
```

**Why This Was Wrong:**
- `entry_price` was fixed from Day 1 (e.g., $1000)
- When rebalancing bought new units, it applied the **entire historical profit** to those new units
- This created "phantom profits"

**Example of the Bug:**
```
Day 1:  Buy 27 units at $1000. entry_price = $1000
Day 50: Price = $1500. You have 27 units.
        P&L = ($1500 - $1000) * 27 = $13,500 ✓ Correct
        
Day 50: Rebalance adds 5 units. Now you have 32 units.
Day 51: Price still $1500.
        P&L = ($1500 - $1000) * 32 = $16,000
        ❌ WRONG! You just gained $2,500 from doing nothing!
        
The 5 new units were bought at $1500, not $1000.
```

### The Solution

**NEW (CORRECT) CODE:**
```python
# Track price changes, not absolute differences
price_change = row['Close'] - self.previous_day_close
market_pnl = self.units * price_change
self.equity += market_pnl - daily_cost
```

**Why This Works:**
- We track the **previous day's close price**
- Each day, we calculate the **change** in price
- P&L = (price change) × (current units)
- This is proper "mark-to-market" accounting

**Same Example with Fix:**
```
Day 50: Price = $1500. You have 27 units.
        previous_day_close = $1480 (example)
        P&L = ($1500 - $1480) * 27 = $540 ✓
        
Day 50: Rebalance adds 5 units. Now you have 32 units.
        previous_day_close = $1500 (updated at end of day)
        
Day 51: Price = $1500 (no change)
        P&L = ($1500 - $1500) * 32 = $0 ✓ Correct!
```

---

## Implementation Architecture

### SOLID Principles Applied

The refactoring follows Clean Architecture and SOLID principles:

#### 1. Single Responsibility Principle (SRP)

**Before:** `run_simulation()` did everything:
- Managed state
- Calculated P&L
- Checked liquidation
- Rebalanced positions
- Recorded data

**After:** Clear separation:
- `LeveragedAccount` class: Domain logic (state + behavior)
- `run_simulation()` function: Orchestration layer
- `calculate_target_units()`: Pure calculation function

#### 2. Domain-Driven Design

```
┌─────────────────────────────────────────┐
│         Presentation Layer              │
│  (Streamlit UI - streamlit_app.py)      │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│        Application Layer                │
│  (run_simulation, run_benchmark)        │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│          Domain Layer                   │
│  (LeveragedAccount, calculate_target    │
│   _units - core business logic)         │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│       Infrastructure Layer              │
│  (yfinance data fetching, caching)      │
└─────────────────────────────────────────┘
```

---

## Mathematical Formulas

### 1. Target Units Calculation

The formula for calculating the maximum safe number of units:

```
N = E / (S × B)

Where:
  N = Target number of units
  E = Current equity ($)
  S = Current asset price ($)
  B = Total buffer (as decimal)
```

**Total Buffer Calculation:**
```
B = MD + (MR × MC) + TC

Where:
  MD = Max market drop to survive (e.g., 0.30 for 30%)
  MR = Margin requirement (0.05 for 5% = 20x leverage)
  MC = Margin closeout (0.50 for 50%)
  TC = Time-adjusted cost buffer (set to 0 in current implementation)
  
Example with defaults:
  B = 0.30 + (0.05 × 0.50) + 0
  B = 0.30 + 0.025 + 0
  B = 0.325 (32.5%)
```

**Full Example:**
```
Given:
  Initial capital: $10,000
  Entry price: $1,116
  Max drop: 30%
  
Calculate:
  B = 0.325
  Cost per unit = $1,116 × 0.325 = $362.70
  N = $10,000 / $362.70 = 27.57 units
```

### 2. Daily Equity Calculation (Post-Refactor)

**Correct Mark-to-Market Method:**
```
For each day t:

1. Price Change:
   ΔP = Close[t] - Close[t-1]

2. Market P&L:
   P&L_market = Units[t] × ΔP

3. Daily Cost:
   Cost_daily = (Close[t] × Units[t]) × (0.0533 / 365)

4. Equity Update:
   Equity[t] = Equity[t-1] + P&L_market - Cost_daily

5. Optional Rebalance:
   if rebalance_today:
       Units[t] = calculate_target_units(Equity[t], Close[t], MaxDrop)
```

### 3. Liquidation Check

**At the Daily Low:**
```
1. Calculate P&L at Low:
   P&L_low = (Low[t] - Close[t-1]) × Units[t]

2. Calculate Equity at Low:
   Equity_low = Equity[t-1] + P&L_low

3. Calculate Required Margin:
   Margin_req = Low[t] × Units[t] × 0.05

4. Calculate Liquidation Trigger:
   Trigger = Margin_req × 0.50

5. Check Liquidation:
   if Equity_low ≤ Trigger:
       LIQUIDATED = True
```

---

## Code Structure

### Key Classes and Functions

#### 1. `LeveragedAccount` (Domain Model)

**Responsibilities:**
- Track account state (equity, units, costs)
- Apply daily price changes
- Check for liquidation
- Execute rebalancing

**Key Methods:**
```python
def __init__(self, capital, initial_units):
    # Initialize account state
    
def apply_daily_tick(self, date, row, params):
    # Process one day of market data
    # 1. Check liquidation at low
    # 2. Calculate P&L at close
    # 3. Apply costs
    # 4. Rebalance if needed
    
def _should_rebalance(self, date, frequency):
    # Determine if today is a rebalancing day
    
def rebalance(self, close_price, params):
    # Calculate and set new target units
```

#### 2. `run_simulation()` (Application Layer)

**Responsibilities:**
- Create and configure `LeveragedAccount`
- Loop through historical data
- Record results for visualization
- Format output DataFrame

**Does NOT:**
- Calculate P&L (delegated to Account)
- Check liquidation (delegated to Account)
- Manage state (delegated to Account)

#### 3. `calculate_target_units()` (Pure Function)

**Responsibilities:**
- Pure calculation: same inputs → same output
- No side effects
- Easy to test

---

## Testing Strategy

### Unit Test Categories

The test suite (`test_leveraged_account.py`) covers:

#### 1. **Target Units Calculation**
- ✓ Correct calculation with various inputs
- ✓ Edge cases (zero values, extreme percentages)
- ✓ Different market prices and equity levels

#### 2. **Daily Tick Processing**
- ✓ Equity updates correctly with price changes
- ✓ Costs are applied correctly
- ✓ Previous close is tracked properly

#### 3. **Liquidation Logic**
- ✓ Liquidation triggers at correct level
- ✓ Account stops updating after liquidation
- ✓ Equity set to trigger level on liquidation

#### 4. **Rebalancing Logic**
- ✓ Daily rebalancing works correctly
- ✓ Units adjust based on equity changes
- ✓ No phantom profits (the bug fix verification!)

#### 5. **Mark-to-Market P&L**
- ✓ Flat market → no P&L change
- ✓ Up market → correct positive P&L
- ✓ Down market → correct negative P&L
- ✓ Rebalancing → P&L calculated correctly on new units

### Running Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
pytest test_leveraged_account.py -v

# Run with coverage
pytest test_leveraged_account.py --cov=streamlit_app --cov-report=html

# Run specific test
pytest test_leveraged_account.py::test_no_phantom_profits -v
```

---

## Performance Considerations

### Time Complexity

- `calculate_target_units()`: O(1) - constant time calculation
- `apply_daily_tick()`: O(1) - constant time per day
- `run_simulation()`: O(n) - linear in number of days

### Space Complexity

- Account state: O(1) - fixed size regardless of data
- Results storage: O(n) - linear in number of days

### Optimization Opportunities

1. **Vectorization**: Could vectorize some calculations using NumPy for large datasets
2. **Caching**: yfinance data is already cached via `@st.cache_data`
3. **Parallel Processing**: Could run multiple scenarios in parallel

---

## Future Enhancements

### 1. Monthly/Quarterly Rebalancing (Partially Implemented)

Currently, the UI supports these options, but `_should_rebalance()` needs completion:

```python
def _should_rebalance(self, date, frequency):
    if frequency == "Daily":
        return True
    elif frequency == "Monthly":
        # TODO: Implement monthly check
        # return date.is_month_start or similar
        pass
    elif frequency == "Quarterly":
        # TODO: Implement quarterly check
        pass
    return False
```

### 2. Transaction Costs

Add explicit transaction costs for buys/sells during rebalancing:

```python
def rebalance(self, close_price, params):
    target_units = calculate_target_units(...)
    unit_change = abs(target_units - self.units)
    transaction_cost = unit_change * close_price * params['tx_cost_pct']
    self.equity -= transaction_cost
    self.units = target_units
```

### 3. Multiple Assets

Extend to track multiple leveraged positions:

```python
class Portfolio:
    def __init__(self, capital):
        self.accounts = {}  # asset_name -> LeveragedAccount
        self.total_equity = capital
```

### 4. Risk Metrics

Add Sharpe ratio, max drawdown, Sortino ratio calculations:

```python
def calculate_risk_metrics(results_df):
    returns = results_df['Leveraged Equity'].pct_change()
    sharpe = returns.mean() / returns.std() * np.sqrt(252)
    max_dd = calculate_max_drawdown(results_df['Leveraged Equity'])
    return {'sharpe': sharpe, 'max_drawdown': max_dd}
```

---

## Conclusion

This implementation provides:

✅ **Correctness**: Bug-free P&L calculations
✅ **Clarity**: Clean, well-documented code
✅ **Testability**: Comprehensive unit test coverage
✅ **Maintainability**: SOLID principles applied
✅ **Extensibility**: Easy to add new features

The refactoring transforms a working prototype into production-quality code that you can trust for real backtesting analysis.

---

## References

- Clean Architecture: Robert C. Martin
- Domain-Driven Design: Eric Evans
- SOLID Principles: Robert C. Martin
- Mark-to-Market Accounting: Standard practice in derivatives trading
