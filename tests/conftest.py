import pytest

pytest_plugins = ["bsm_test_utils.fixtures"]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-upstream-api",
        action="store_true",
        default=False,
        help="Run tests that contact the live Minecraft download API",
    )
    parser.addoption(
        "--run-benchmarks",
        action="store_true",
        default=False,
        help="Run large dataset backup/restore benchmark tests",
    )
