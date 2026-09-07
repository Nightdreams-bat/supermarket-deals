from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class Offer:
    retailer: str
    product: str
    brand: str | None
    price: float | None
    old_price: float | None
    discount_pct: float | None
    valid_from: date | None
    valid_to: date | None
    url: str | None

    def key(self) -> str:
        return f"{self.retailer}|{self.product}|{self.valid_to}"


class Source(ABC):
    name: str

    @abstractmethod
    def fetch_offers(self) -> list[Offer]:
        ...
