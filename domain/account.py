from datetime import date
from typing import Optional
from domain.constants import MARGIN_REQ_DECIMAL, MARGIN_CLOSEOUT_DECIMAL


class LeveragedAccount:
    def __init__(self, capital: float, initial_units: float):
        self.equity = capital
        self.units = initial_units
        self.initial_capital = capital
        self.cumulative_cost = 0.0
        self.liquidated = False
        self.liquidation_date: Optional[date] = None
        self.previous_day_close = 0.0
        self.previous_month: Optional[int] = None
        self.previous_quarter: Optional[int] = None

    def apply_daily_tick(self, current_date: date, low: float, close: float, 
                         daily_coc: float, rebalance_frequency: str, 
                         max_drop_percent: float) -> None:
        if self.liquidated:
            return

        self._check_liquidation(current_date, low)
        if self.liquidated:
            return

        self._update_equity(close, daily_coc)
        
        if self._should_rebalance(current_date, rebalance_frequency):
            self._rebalance(close, max_drop_percent)

        self.previous_day_close = close

    def _check_liquidation(self, current_date: date, low: float) -> None:
        pnl_at_low = (low - self.previous_day_close) * self.units
        equity_at_low = self.equity + pnl_at_low
        
        required_margin = (low * self.units) * MARGIN_REQ_DECIMAL
        liquidation_trigger = required_margin * MARGIN_CLOSEOUT_DECIMAL

        if equity_at_low <= liquidation_trigger:
            self.liquidated = True
            self.liquidation_date = current_date
            self.equity = liquidation_trigger

    def _update_equity(self, close: float, daily_coc: float) -> None:
        price_change = close - self.previous_day_close
        market_pnl = self.units * price_change
        
        position_value_at_close = close * self.units
        daily_cost = position_value_at_close * daily_coc
        
        self.equity += market_pnl - daily_cost
        self.cumulative_cost -= daily_cost

    def _should_rebalance(self, current_date: date, frequency: str) -> bool:
        if frequency == "Never":
            return False
        
        if frequency == "Daily":
            return True

        if frequency == "Monthly":
            current_month = current_date.month
            if self.previous_month is None:
                self.previous_month = current_month
                return False
            
            should_rebalance = current_month != self.previous_month
            self.previous_month = current_month
            return should_rebalance
        
        if frequency == "Quarterly":
            current_quarter = (current_date.month - 1) // 3 + 1
            if self.previous_quarter is None:
                self.previous_quarter = current_quarter
                return False
            
            should_rebalance = current_quarter != self.previous_quarter
            self.previous_quarter = current_quarter
            return should_rebalance
        
        return False

    def _rebalance(self, close_price: float, max_drop_percent: float) -> None:
        from domain.calculations import calculate_target_units
        target_units = calculate_target_units(
            self.equity, 
            close_price, 
            max_drop_percent
        )
        self.units = target_units
