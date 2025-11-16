import pytest
from datetime import date
from domain.account import LeveragedAccount


@pytest.mark.parametrize(
    "test_case",
    [
        pytest.param(
            {
                "capital": 10000.0,
                "initial_units": 30.0,
                "low": 900.0,
                "close": 950.0,
                "previous_close": 1000.0,
                "daily_coc": 0.0533 / 365.0,
                "should_liquidate": False,
            },
            id="no_liquidation_equity_above_trigger",
        ),
        pytest.param(
            {
                "capital": 10000.0,
                "initial_units": 30.0,
                "low": 600.0,
                "close": 650.0,
                "previous_close": 1000.0,
                "daily_coc": 0.0533 / 365.0,
                "should_liquidate": True,
            },
            id="liquidation_triggered_by_low_price",
        ),
        pytest.param(
            {
                "capital": 5000.0,
                "initial_units": 15.0,
                "low": 950.0,
                "close": 1000.0,
                "previous_close": 1000.0,
                "daily_coc": 0.0533 / 365.0,
                "should_liquidate": False,
            },
            id="no_price_change_no_liquidation",
        ),
    ],
)
def test_account_liquidation(test_case):
    account = LeveragedAccount(test_case["capital"], test_case["initial_units"])
    account.previous_day_close = test_case["previous_close"]
    
    account.apply_daily_tick(
        date(2020, 1, 1),
        test_case["low"],
        test_case["close"],
        test_case["daily_coc"],
        "Never",
        30.0
    )
    
    assert account.liquidated == test_case["should_liquidate"]


@pytest.mark.parametrize(
    "test_case",
    [
        pytest.param(
            {
                "capital": 10000.0,
                "initial_units": 30.0,
                "close": 1100.0,
                "previous_close": 1000.0,
                "daily_coc": 0.0533 / 365.0,
                "expected_pnl": 3000.0,
            },
            id="positive_price_movement",
        ),
        pytest.param(
            {
                "capital": 10000.0,
                "initial_units": 30.0,
                "close": 900.0,
                "previous_close": 1000.0,
                "daily_coc": 0.0533 / 365.0,
                "expected_pnl": -3000.0,
            },
            id="negative_price_movement",
        ),
        pytest.param(
            {
                "capital": 10000.0,
                "initial_units": 30.0,
                "close": 1000.0,
                "previous_close": 1000.0,
                "daily_coc": 0.0533 / 365.0,
                "expected_pnl": 0.0,
            },
            id="no_price_movement",
        ),
    ],
)
def test_account_equity_update(test_case):
    account = LeveragedAccount(test_case["capital"], test_case["initial_units"])
    account.previous_day_close = test_case["previous_close"]
    
    initial_equity = account.equity
    
    account.apply_daily_tick(
        date(2020, 1, 1),
        test_case["close"],
        test_case["close"],
        test_case["daily_coc"],
        "Never",
        30.0
    )
    
    expected_cost = test_case["close"] * test_case["initial_units"] * test_case["daily_coc"]
    expected_equity = initial_equity + test_case["expected_pnl"] - expected_cost
    
    assert account.equity == pytest.approx(expected_equity, rel=1e-6)


@pytest.mark.parametrize(
    "test_case",
    [
        pytest.param(
            {
                "frequency": "Never",
                "dates": [date(2020, 1, 1), date(2020, 1, 2), date(2020, 2, 1)],
                "expected_rebalances": 0,
            },
            id="never_rebalance",
        ),
        pytest.param(
            {
                "frequency": "Daily",
                "dates": [date(2020, 1, 1), date(2020, 1, 2), date(2020, 1, 3)],
                "expected_rebalances": 3,
            },
            id="daily_rebalance",
        ),
        pytest.param(
            {
                "frequency": "Monthly",
                "dates": [date(2020, 1, 1), date(2020, 1, 15), date(2020, 2, 1), date(2020, 3, 1)],
                "expected_rebalances": 2,
            },
            id="monthly_rebalance",
        ),
        pytest.param(
            {
                "frequency": "Quarterly",
                "dates": [date(2020, 1, 1), date(2020, 2, 1), date(2020, 4, 1), date(2020, 7, 1)],
                "expected_rebalances": 2,
            },
            id="quarterly_rebalance",
        ),
    ],
)
def test_rebalancing_frequency(test_case):
    account = LeveragedAccount(10000.0, 30.0)
    account.previous_day_close = 1000.0
    
    rebalance_count = 0
    initial_units = account.units
    
    for test_date in test_case["dates"]:
        account.apply_daily_tick(
            test_date,
            1000.0,
            1050.0,
            0.0533 / 365.0,
            test_case["frequency"],
            30.0
        )
        if account.units != initial_units:
            rebalance_count += 1
            initial_units = account.units
    
    assert rebalance_count == test_case["expected_rebalances"]
