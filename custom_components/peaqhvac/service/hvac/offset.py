from __future__ import annotations

import logging
from statistics import mean
from typing import Tuple
import custom_components.peaqhvac.service.hvac.peakfinder as peakfinder
from peaqevcore.services.hourselection.hoursselection import Hoursselection
from datetime import timedelta, datetime
from custom_components.peaqhvac.service.hub.weather_prognosis import PrognosisExportModel
from custom_components.peaqhvac.service.models.offset_model import OffsetModel

_LOGGER = logging.getLogger(__name__)


class Offset:
    """The class that provides the offsets for the hvac"""
    def __init__(self, hub):
        self.hours = Hoursselection()
        self._hub = hub
        self.model = OffsetModel()

    def get_offset(
            self,
            prices: list,
            prices_tomorrow: list
    ) -> Tuple[dict, dict]:
        """External entrypoint to the class"""
        if any(
                [
                    self.hours.prices != prices,
                    self.hours.prices_tomorrow != prices_tomorrow,
                    self.model.calculated_offsets == {}, {},
                    self._hub.options.hvac_tolerance != self.model.tolerance,
                    self._hub.prognosis.prognosis != self.model.prognosis
                ]
        ):
            self._set_internal_parameters(prices, prices_tomorrow)
            if 23 <= len(prices) <= 25:
                self.model.raw_offsets = self._update_offset()
            else:
                _LOGGER.error(f"The pricelist for today was not between 23 and 25 hours long. Cannot calculate offsets. length: {len(prices)}")
            try:
                _weather_dict = self._get_weatherprognosis_adjustment(self.model.raw_offsets)
                _weather_inverted = {k: v*-1 for (k, v) in _weather_dict[0].items()}
                self.model.calculated_offsets = self._update_offset(_weather_inverted)
            except Exception as e:
                _LOGGER.warning(f"Unable to calculate prognosis-offsets. Setting normal calculation: {e}")
                self.model.calculated_offsets = self.model.raw_offsets
        return self.model.calculated_offsets

    def _set_internal_parameters(self, prices, prices_tomorrow) -> None:
        self.hours.prices = prices
        self.hours.prices_tomorrow = prices_tomorrow
        self.model.prognosis = self._hub.prognosis.prognosis
        self.model.tolerance = self._hub.options.hvac_tolerance

    def _update_offset(
            self,
            weather_adjusted_today=None
    ) -> Tuple[dict, dict]:
        try:
            d = self.hours.offsets
            today = self._offset_per_day(d['today']) if weather_adjusted_today is None else weather_adjusted_today
            tomorrow = {}
            if len(d['tomorrow']) > 0:
                tomorrow = self._offset_per_day(d['tomorrow'])
            return Offset._smooth_transitions(today, tomorrow, self.model.tolerance)
        except Exception as e:
            _LOGGER.exception(f"Exception while trying to calculate offset: {e}")
            return {}, {}

    def _offset_per_day(
            self,
            day_values: dict
    ) -> dict:
        ret = {}
        try:
            _max_today = max(day_values.values())
            _min_today = min(day_values.values())
            factor = max(abs(_max_today), abs(_min_today)) / self.model.tolerance

            for k, v in day_values.items():
                ret[k] = int(round((day_values[k] / factor) * -1, 0))
        except Exception as e:
            _LOGGER.exception(f"Could not calculate per-day offset correctly: {e}")
        return ret

    def _get_two_hour_prog(
            self,
            thishour: datetime
    ) -> PrognosisExportModel | None:
        for p in self._hub.prognosis.prognosis:
            c = timedelta.total_seconds(p.DT - thishour)
            if c == 10800:
                return p
        return None

    def _get_weatherprognosis_adjustment(
            self,
            offsets
    ) -> Tuple[dict, dict]:
        self._hub.prognosis.update_weather_prognosis()
        ret = {}, offsets[1]
        for k, v in offsets[0].items():
            now = datetime.now()
            _next_prognosis = self._get_two_hour_prog(
                datetime(now.year, now.month, now.day, int(k), 0, 0)
            )
            if _next_prognosis is not None and int(k) >= now.hour:
                divisor = max((11 - _next_prognosis.TimeDelta) / 10, 0)
                adj = int(round((_next_prognosis.delta_temp_from_now / 2.5) * divisor, 0)) * -1
                if adj != 0:
                    if (v + adj) <= 0:
                        ret[0][k] = (v + adj) *-1
                    else:
                        ret[0][k] = (v + adj) * -1
                else:
                    ret[0][k] = v * -1
            else:
                ret[0][k] = v * -1
        return ret

    @staticmethod
    def adjust_to_threshold(adjustment: int, tolerance: int) -> int:
        return int(round(min(adjustment, tolerance) if adjustment >= 0 else max(adjustment, tolerance * -1), 0))

    def _getaverage(self, prices: list, prices_tomorrow: list = None) -> float:
        try:
            total = prices
            self.model.peaks_today = peakfinder.identify_peaks(prices)
            prices_tomorrow_cleaned = Offset._sanitize_pricelists(prices_tomorrow)
            if len(prices_tomorrow_cleaned) == 24:
                total.extend(prices_tomorrow_cleaned)
            return mean(total)
        except Exception as e:
            _LOGGER.exception(f"Could not set offset. prices: {prices}, prices_tomorrow: {prices_tomorrow}. {e}")
            return 0.0

    @staticmethod
    def _sanitize_pricelists(inputlist) -> list:
        if inputlist is None or len(inputlist) < 24:
            return []
        for i in inputlist:
            if not isinstance(i, (float, int)):
                return []
        return inputlist

    @staticmethod
    def _find_single_anomalies(
            adj: list
    ) -> list[int]:
        for idx, p in enumerate(adj):
            if idx <= 1 or idx >= len(adj) - 1:
                pass
            else:
                if all([
                    adj[idx - 1] == adj[idx + 1],
                    adj[idx - 1] != adj[idx]
                ]):
                    _prev = adj[idx - 1]
                    _curr = adj[idx]
                    diff = max(_prev, _curr) - min(_prev, _curr)
                    if int(diff / 2) > 0:
                        if _prev > _curr:
                            adj[idx] += int(diff / 2)
                        else:
                            adj[idx] -= int(diff / 2)
        return adj

    @staticmethod
    def _smooth_transitions(
            today: dict,
            tomorrow: dict,
            tolerance: int
    ) -> Tuple[dict, dict]:
        tolerance = min(tolerance, 4)
        start_list = []
        start_list.extend(today.values())
        start_list.extend(tomorrow.values())

        # Find and remove single anomalies.
        start_list = Offset._find_single_anomalies(start_list)
        # Smooth out transitions upwards so that there is less risk of electrical addon usage.
        for idx, v in enumerate(start_list):
            if idx < len(start_list) - 1:
                if start_list[idx + 1] >= start_list[idx] + tolerance:
                    start_list[idx] += 1
        # Package it and return
        ret = {}, {}
        for hour in range(0, 24):
            ret[0][hour] = start_list[hour]
        if len(tomorrow.items()) == 24:
            for hour in range(24, 48):
                ret[1][hour - 24] = start_list[hour]
        return ret