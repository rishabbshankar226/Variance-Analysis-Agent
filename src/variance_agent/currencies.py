"""Explicit reporting units; this module performs no currency conversion."""

CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}
SYMBOL_CURRENCIES = {symbol: code for code, symbol in CURRENCY_SYMBOLS.items()}


def validate_currency(value: object) -> str:
    if not isinstance(value, str) or value not in CURRENCY_SYMBOLS:
        raise ValueError("Reporting currency must be USD, EUR, or GBP; no FX conversion is performed.")
    return value
