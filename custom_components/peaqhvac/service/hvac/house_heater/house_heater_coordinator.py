from __future__ import annotations

import logging
import asyncio
from typing import Tuple
from custom_components.peaqhvac.service.hub.target_temp import adjusted_tolerances
from custom_components.peaqhvac.service.hvac.const import HOUSE_HEATER_NAME
from custom_components.peaqhvac.service.hvac.house_heater.house_heater_helpers import HouseHeaterHelpers
from custom_components.peaqhvac.service.hvac.house_heater.models.calculated_offset import CalculatedOffsetModel
from custom_components.peaqhvac.service.hvac.house_heater.models.offset_adjustments import OffsetAdjustments
from custom_components.peaqhvac.service.hvac.house_heater.temperature_helper import get_tempdiff_inverted, get_temp_trend_offset
from custom_components.peaqhvac.service.hvac.interfaces.iheater import IHeater
from custom_components.peaqhvac.service.hvac.offset.offset_utils import adjust_to_threshold
from custom_components.peaqhvac.service.models.enums.demand import Demand
from peaqevcore.common.models.observer_types import ObserverTypes

from custom_components.peaqhvac.service.models.enums.hvacoperations import HvacOperations

_LOGGER = logging.getLogger(__name__)

OFFSET_MIN_VALUE = -10


class HouseHeaterCoordinator(IHeater):
    def __init__(self, hvac, hub, observer, options, sensors):
        self._lock = asyncio.Lock()
        self._current_adjusted_offset: int = 0
        self._calculated_offsetdata: CalculatedOffsetModel = CalculatedOffsetModel(0,0,0)
        self._helpers = HouseHeaterHelpers(hvac=hvac) #todo: can probably be a module instead
        super().__init__(hub=hub, observer=observer, options=options, sensors=sensors, implementation=HOUSE_HEATER_NAME)

    @property
    def aux_offset_adjustments(self) -> dict:
        return self._helpers.aux_offset_adjustments

    @property
    def current_adjusted_offset(self) -> int:
        return int(self._current_adjusted_offset)

    @current_adjusted_offset.setter
    def current_adjusted_offset(self, val) -> None:
        if isinstance(val, (float, int)):
            self._current_adjusted_offset = val

    @property
    def is_initialized(self) -> bool:
        return True

    @IHeater.demand.setter
    def demand(self, val):
        self._demand = val

    def turn_off_all_heat(self) -> bool:
        return self._sensors.average_temp_outdoors.value > self._options.heating.outdoor_temp_stop_heating

    def _update_aux_offset_adjustments(self, max_lower: bool) -> None:
        self._helpers.aux_offset_adjustments[OffsetAdjustments.PeakHour] = OFFSET_MIN_VALUE if max_lower else 0
        self.current_adjusted_offset = OFFSET_MIN_VALUE

    async def async_adjusted_offset(self, current_offset: int) -> Tuple[int, bool]:
        """Calculates the adjusted offset taking temp diffs etc into account."""
        async with self._lock:
            outdoor_temp = self._sensors.average_temp_outdoors.value
            temp_diff = self._sensors.get_tempdiff()

            max_lower = self.hub.offset.max_price_lower(temp_diff)
            if (self.turn_off_all_heat() or max_lower) and outdoor_temp >= 0:
                self._update_aux_offset_adjustments(max_lower)
                return self.current_adjusted_offset, True

            self._helpers.aux_offset_adjustments[OffsetAdjustments.PeakHour] = 0

            offset_data = await self.async_calculated_offsetdata(current_offset)
            force_update = self._helpers.temporarily_lower_offset(offset_data)

            if self.current_adjusted_offset != round(offset_data.sum_values(), 0):
                ret = adjust_to_threshold(
                    offset_data,
                    self._sensors.average_temp_outdoors.value,
                    self.hub.offset.model.tolerance
                )
                self.current_adjusted_offset = round(ret, 0)

        return self.current_adjusted_offset, force_update

    def _get_demand(self) -> Demand:
        return self._helpers.helper_get_demand()

    async def async_calculated_offsetdata(self, current_offset: int) -> CalculatedOffsetModel:
        def __current_tolerances(determinator: bool, current_offset: int, adjust_tolerances: bool = True) -> float:
            _min, _max = self._sensors.tolerances
            if adjust_tolerances:
                tolerances = adjusted_tolerances(current_offset,_min, _max)
            else:
                tolerances = _min, _max
            return tolerances[0] if (determinator > 0 or determinator is True) else tolerances[1]

        temp_diff = get_tempdiff_inverted(
            current_offset,
            self._sensors.get_tempdiff(),
            self._sensors.get_min_indoors_diff(),
            __current_tolerances
        )

        temp_trend = get_temp_trend_offset(
            do_calc=self._sensors.temp_trend_indoors.is_clean,
            temp_diff_offset=temp_diff,
            predicted_temp=self._sensors.predicted_temp,
            adjusted_temp=self._sensors.set_temp_indoors.adjusted_temp
        )

        ret = CalculatedOffsetModel(current_offset=current_offset,
                                    current_tempdiff=temp_diff,
                                    current_temp_trend_offset=temp_trend)
        self._calculated_offsetdata = ret
        return ret

    async def async_update_operation(self):
        pass
