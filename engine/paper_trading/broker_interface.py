"""
Broker-interface. I denna version finns ENDAST PaperBroker.

LiveBroker existerar som ett interface för framtiden, men är permanent
inaktiverad (raise NotImplementedError). Att aktivera riktig handel kräver
en explicit, medveten kodändring här - det kan aldrig ske av misstag.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from engine.paper_trading.paper_trading import open_trade_from_signal, monitor_open_trades


class BrokerInterface(ABC):
    @abstractmethod
    def place_order(self, signal: dict) -> dict | None: ...

    @abstractmethod
    def check_open_positions(self, latest_candle: dict, symbol: str) -> list[dict]: ...


class PaperBroker(BrokerInterface):
    """Simulerad broker - inga riktiga pengar, ingen extern anslutning."""

    def place_order(self, signal: dict) -> dict | None:
        return open_trade_from_signal(signal)

    def check_open_positions(self, latest_candle: dict, symbol: str) -> list[dict]:
        return monitor_open_trades(latest_candle, symbol)


class LiveBroker(BrokerInterface):
    """
    PERMANENT INAKTIVERAD I DENNA VERSION.

    Att koppla in en riktig broker kräver:
    1. En explicit, granskad kodändring av denna klass.
    2. Riskvalidering och godkännande utanför systemet.
    3. Borttagning av NotImplementedError nedan.

    Detta är en medveten säkerhetsspärr - systemet får aldrig av misstag
    skicka riktiga order.
    """

    def place_order(self, signal: dict) -> dict | None:
        raise NotImplementedError(
            "LiveBroker är inaktiverad. Detta system är byggt för paper trading "
            "(simulerad handel) och får inte skicka riktiga broker-order i denna version."
        )

    def check_open_positions(self, latest_candle: dict, symbol: str) -> list[dict]:
        raise NotImplementedError("LiveBroker är inaktiverad.")


def get_active_broker() -> BrokerInterface:
    """Enda platsen i systemet som väljer broker. Alltid PaperBroker i v1."""
    return PaperBroker()
