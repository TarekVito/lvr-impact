import pandas as pd
from domain.account import LeveragedAccount
from domain.calculations import calculate_target_units
from domain.constants import COST_OF_CARRY_DECIMAL, MARGIN_REQ_DECIMAL, MARGIN_CLOSEOUT_DECIMAL
from domain.models import SimulationResult, BenchmarkResult


class SimulationService:
    def run_leveraged_simulation(
        self,
        capital: float,
        initial_units: float,
        entry_price: float,
        historical_data: pd.DataFrame,
        rebalance_frequency: str,
        max_drop_percent: float
    ) -> tuple[pd.DataFrame, SimulationResult]:
        daily_coc = COST_OF_CARRY_DECIMAL / 365.0
        
        account = LeveragedAccount(capital, initial_units)
        account.previous_day_close = entry_price

        dates = []
        equity_values = []
        unit_values = []
        cost_values = []
        action_values = []
        trigger_values = []
        unit_change_values = []

        for current_date, row in historical_data.iterrows():
            units_before = account.units
            
            account.apply_daily_tick(
                current_date,
                row['Low'],
                row['Close'],
                daily_coc,
                rebalance_frequency,
                max_drop_percent
            )
            
            dates.append(current_date)
            equity_values.append(account.equity)
            cost_values.append(account.cumulative_cost)
            unit_values.append(account.units)
            
            unit_change = account.units - units_before
            if unit_change > 0.01:
                action = "Buy"
            elif unit_change < -0.01:
                action = "Sell"
            else:
                action = "Hold"
                unit_change = 0.0
            
            action_values.append(action)
            unit_change_values.append(unit_change)

            req_margin = (row['Close'] * account.units) * MARGIN_REQ_DECIMAL
            trigger = req_margin * MARGIN_CLOSEOUT_DECIMAL
            trigger_values.append(trigger)
            
            if account.liquidated:
                break

        results_df = pd.DataFrame(
            {
                'Leveraged Equity': equity_values,
                'Cumulative Cost': cost_values,
                'Liquidation Trigger Level': trigger_values,
                'Units Held': unit_values,
                'Unit Change': unit_change_values,
                'Rebalance Action': action_values
            },
            index=pd.to_datetime(dates)
        )
        
        summary = SimulationResult(
            liquidated=account.liquidated,
            liquidation_date=account.liquidation_date,
            final_equity=account.equity,
            total_return_pct=((account.equity / capital) - 1) * 100,
            total_costs_paid=-account.cumulative_cost,
            initial_units=initial_units
        )
        
        return results_df, summary

    def run_benchmark_simulation(
        self,
        capital: float,
        entry_price: float,
        historical_data: pd.DataFrame
    ) -> tuple[pd.DataFrame, BenchmarkResult]:
        benchmark_units = capital / entry_price
        benchmark_equity = benchmark_units * historical_data['Close']
        
        results_df = pd.DataFrame({'Equity': benchmark_equity})
        
        final_equity = results_df['Equity'].iloc[-1] if not results_df.empty else 0.0
        total_return = ((final_equity / capital) - 1) * 100 if capital > 0 else 0.0
        
        summary = BenchmarkResult(
            final_equity=final_equity,
            total_return_pct=total_return,
            units_held=benchmark_units
        )
        
        return results_df, summary
