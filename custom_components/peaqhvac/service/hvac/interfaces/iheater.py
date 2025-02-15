from __future__ import annotations

from typing import TYPE_CHECKING

from peaqevcore.common.wait_timer import WaitTimer

if TYPE_CHECKING:
    from custom_components.peaqhvac.service.hvac.interfaces.ihvac import IHvac

import logging
from abc import ABC, abstractmethod
from peaqevcore.models.hub.hubmember import HubMember
from custom_components.peaqhvac.service.models.enums.demand import Demand

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = 60
class IHeater(ABC):

    def __init__(self, hvac: IHvac):
        self._demand: Demand = Demand.NoDemand
        self._hvac: IHvac = hvac
        self._control_module: HubMember = HubMember(data_type=bool, initval=False)
        self._latest_update = WaitTimer(timeout=UPDATE_INTERVAL)

    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        pass

    @property
    def demand(self) -> Demand:
        if self._demand is not None:
            return self._demand
        _LOGGER.error(f"{__name__} had no value for Demand.")
        return Demand.NoDemand

    @property
    def control_module(self) -> bool:
        return self._control_module.value

    @control_module.setter
    def control_module(self, val) -> None:
        self._control_module.value = val

    def _get_demand_for_current_hour(self) -> Demand:
        # if vacation or similar, return NoDemand
        pass

    async def async_update_demand(self):
        if self._latest_update.is_timeout():
            self._latest_update.update()
            self._demand = self._get_demand()
            if self.control_module:
                await self.async_update_operation()

    @abstractmethod
    def _get_demand(self):
        pass

    @abstractmethod
    async def async_update_operation(self):
        pass

    # def compare to heating demand
    # def get current water temp from nibe
    # def turn on waterboost or not
