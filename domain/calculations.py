from domain.constants import MARGIN_REQ_DECIMAL, MARGIN_CLOSEOUT_DECIMAL


def calculate_target_units(equity: float, current_price: float, 
                           max_market_drop_percent: float) -> float:
    md_decimal = max_market_drop_percent / 100.0
    broker_buffer_decimal = MARGIN_REQ_DECIMAL * MARGIN_CLOSEOUT_DECIMAL
    cost_buffer_decimal = 0.0

    total_buffer_decimal = md_decimal + broker_buffer_decimal + cost_buffer_decimal

    if total_buffer_decimal <= 0:
        return 0.0

    total_cost_and_buffer_per_unit = current_price * total_buffer_decimal

    if total_cost_and_buffer_per_unit <= 0:
        return 0.0
        
    return equity / total_cost_and_buffer_per_unit
