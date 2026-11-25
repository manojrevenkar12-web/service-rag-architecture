"""Tools the assistant may call. Stock comes from the ERP, never from a manual or a model."""

from __future__ import annotations

from typing import Protocol


class StockService(Protocol):
    def available(self, part: str, warehouse: str) -> int | None: ...


class DictStock:
    def __init__(self, stock: dict[tuple[str, str], int]) -> None:
        self.stock = stock
        self.calls = 0

    def available(self, part: str, warehouse: str) -> int | None:
        self.calls += 1
        return self.stock.get((part, warehouse))


class ProductRegistry(Protocol):
    def known(self, model: str) -> bool: ...
    def by_order_number(self, order_number: str) -> str | None: ...


class DictRegistry:
    def __init__(self, models: set[str], order_numbers: dict[str, str]) -> None:
        self.models = models
        self.order_numbers = order_numbers
        self.calls = 0

    def known(self, model: str) -> bool:
        return model in self.models

    def by_order_number(self, order_number: str) -> str | None:
        self.calls += 1
        return self.order_numbers.get(order_number)
