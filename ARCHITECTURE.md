# Architecture Documentation

## Overview

This project follows **Clean Architecture** principles with clear separation of concerns across three main layers:

- **Domain Layer**: Core business logic and entities (no external dependencies)
- **Application Layer**: Use cases and orchestration (depends only on Domain)
- **Infrastructure Layer**: External concerns like UI, data sources, APIs (depends on Application and Domain)

## Project Structure

```
├── domain/                      # Domain Layer (Core Business Logic)
│   ├── __init__.py
│   ├── constants.py            # Business constants and configuration
│   ├── models.py               # Pydantic models for data validation
│   ├── account.py              # LeveragedAccount entity
│   └── calculations.py         # Pure calculation functions
│
├── application/                 # Application Layer (Use Cases)
│   ├── __init__.py
│   └── simulation_service.py   # Orchestrates simulations
│
├── infrastructure/              # Infrastructure Layer (External Concerns)
│   ├── __init__.py
│   ├── data_adapter.py         # Market data fetching (yfinance)
│   └── ui/
│       ├── __init__.py
│       └── components.py       # Streamlit UI components
│
├── tests/                       # Unit Tests
│   ├── __init__.py
│   ├── test_calculations.py    # Tests for domain calculations
│   └── test_account.py         # Tests for LeveragedAccount
│
├── streamlit_app.py            # Application entry point
└── requirements.txt            # Project dependencies
```

## Layer Responsibilities

### Domain Layer (`domain/`)

**Purpose**: Contains the core business logic with zero external dependencies.

**Files**:
- `constants.py`: Business constants (margin requirements, costs, ticker)
- `models.py`: Pydantic models for type-safe data transfer
- `account.py`: `LeveragedAccount` entity that manages account state and logic
- `calculations.py`: Pure functions for calculations (e.g., `calculate_target_units`)

**Key Principles**:
- No imports from `application/` or `infrastructure/`
- Pure business logic
- No framework dependencies (no Streamlit, no pandas in core logic)

### Application Layer (`application/`)

**Purpose**: Orchestrates business logic to fulfill specific use cases.

**Files**:
- `simulation_service.py`: `SimulationService` class that runs simulations

**Key Principles**:
- Depends on Domain layer only
- Coordinates domain entities and calculations
- Returns Pydantic models for type safety

### Infrastructure Layer (`infrastructure/`)

**Purpose**: Handles all external concerns and framework-specific code.

**Files**:
- `data_adapter.py`: `MarketDataAdapter` for fetching data from yfinance
- `ui/components.py`: `UIComponents` class with all Streamlit rendering logic

**Key Principles**:
- Can depend on both Application and Domain layers
- Contains all framework-specific code (Streamlit, yfinance)
- Implements adapters for external services

## Design Patterns

### Single Responsibility Principle (SRP)
Each class/module has one clear responsibility:
- `LeveragedAccount`: Manages account state and daily operations
- `SimulationService`: Orchestrates simulation execution
- `UIComponents`: Renders UI elements
- `MarketDataAdapter`: Fetches market data

### Dependency Inversion Principle (DIP)
Dependencies point inward:
```
Infrastructure → Application → Domain
```

### Data Validation with Pydantic
All data crossing boundaries uses Pydantic models:
- `SimulationParams`: Input validation
- `SimulationResult`: Leveraged strategy output
- `BenchmarkResult`: Benchmark strategy output

## Testing Strategy

### Unit Tests with pytest.mark.parametrize

All tests use the `@pytest.mark.parametrize` decorator for data-driven testing:

**Example from `test_calculations.py`**:
```python
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
        # More test cases...
    ],
)
def test_calculate_target_units(test_case):
    result = calculate_target_units(
        test_case["equity"],
        test_case["current_price"],
        test_case["max_drop_percent"]
    )
    assert result == pytest.approx(test_case["expected_output"], rel=1e-6)
```

### Test Coverage
- `test_calculations.py`: Tests for pure calculation functions
- `test_account.py`: Tests for `LeveragedAccount` entity logic
  - Liquidation scenarios
  - Equity updates
  - Rebalancing frequency

## Running the Application

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Tests
```bash
pytest tests/ -v
```

### Run Application
```bash
streamlit run streamlit_app.py
```

## Benefits of This Architecture

1. **Testability**: Domain logic is isolated and easily testable
2. **Maintainability**: Clear separation makes changes easier
3. **Flexibility**: Can swap UI or data sources without changing business logic
4. **Type Safety**: Pydantic models provide runtime validation
5. **Scalability**: Easy to add new features in appropriate layers

## Migration Notes

The original monolithic `streamlit_app.py` (~600 lines) has been refactored into:
- Domain layer: 4 focused modules
- Application layer: 1 service class
- Infrastructure layer: 2 adapter modules
- Main entry point: ~120 lines (clean orchestration)
- Comprehensive test suite with parameterized tests

All functionality is preserved while significantly improving code organization and maintainability.
