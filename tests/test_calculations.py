import pytest
from domain.calculations import calculate_target_units


@pytest.mark.parametrize(
    "test_case",
    [
        pytest.param(
            {
                "equity": 10000.0,
                "current_price": 1000.0,
                "max_drop_percent": 30.0,
                "expected_output": 30.769230769230766,
            },
            id="basic_calculation_30_percent_drop",
        ),
        pytest.param(
            {
                "equity": 5000.0,
                "current_price": 500.0,
                "max_drop_percent": 50.0,
                "expected_output": 19.230769230769234,
            },
            id="higher_drop_percentage",
        ),
        pytest.param(
            {
                "equity": 10000.0,
                "current_price": 100.0,
                "max_drop_percent": 10.0,
                "expected_output": 800.0,
            },
            id="low_drop_percentage",
        ),
        pytest.param(
            {
                "equity": 1000.0,
                "current_price": 1000.0,
                "max_drop_percent": 70.0,
                "expected_output": 1.3793103448275863,
            },
            id="maximum_drop_percentage",
        ),
        pytest.param(
            {
                "equity": 0.0,
                "current_price": 1000.0,
                "max_drop_percent": 30.0,
                "expected_output": 0.0,
            },
            id="zero_equity",
        ),
    ],
)
def test_calculate_target_units(test_case):
    result = calculate_target_units(
        test_case["equity"],
        test_case["current_price"],
        test_case["max_drop_percent"]
    )
    assert result == pytest.approx(test_case["expected_output"], rel=1e-6)
