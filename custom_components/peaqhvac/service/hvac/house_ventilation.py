from datetime import datetime, timedelta
import logging
from custom_components.peaqhvac.service.hvac.const import WAITTIMER_TIMEOUT, WAITTIMER_VENT
from peaqevcore.common.wait_timer import WaitTimer
from custom_components.peaqhvac.service.models.enums.hvac_presets import HvacPresets
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)


class HouseVentilation:
    def __init__(self, hvac):
        self._hvac = hvac
        self._wait_timer_boost = WaitTimer(timeout=WAITTIMER_VENT)
        self._current_vent_state: bool = False
        async_track_time_interval(self._hvac.hub.hass, self.async_check_vent_boost, timedelta(seconds=30))

    @property
    def vent_boost(self) -> bool:
        #_LOGGER.debug(f"Vent boost state: {self._current_vent_state}")
        return self._current_vent_state

    async def async_check_vent_boost(self, caller=None) -> None:
        if self._hvac.hub.sensors.temp_trend_indoors.is_clean and self._wait_timer_boost.is_timeout():
            if self._vent_boost_warmth():
                self._vent_boost_start("Vent boosting because of warmth.")
            elif self._vent_boost_night_cooling():
                self._vent_boost_start("Vent boost night cooling")
            elif self._vent_boost_low_dm():
                self._vent_boost_start("Vent boosting because of low degree minutes.")
            else:
                #_LOGGER.debug("all vent boost conditions returned false")
                self._current_vent_state = False
        # else:
        #     self._current_vent_state = False
        if self._hvac.hvac_dm < self._hvac.hub.options.heating_options.low_degree_minutes + 100 or self._hvac.hub.sensors.average_temp_outdoors.value < self._hvac.hub.options.heating_options.very_cold_temp:
            # If HVAC degree minutes are high or outdoor temperature is very cold, stop vent boosting
            _LOGGER.debug(f"low dm or very cold. stopping went boost. dm: {self._hvac.hvac_dm} < {self._hvac.hub.options.heating_options.low_degree_minutes + 100}, temp: {self._hvac.hub.sensors.average_temp_outdoors.value}")
            self._current_vent_state = False
            self._hvac.hub.observer.broadcast("update operation")

    def _vent_boost_warmth(self) -> bool:
        return all(
                    [
                        self._hvac.hub.sensors.get_tempdiff() > 3,
                        self._hvac.hub.sensors.temp_trend_indoors.gradient >= 0,
                        self._hvac.hub.sensors.temp_trend_outdoors.gradient >= 0,
                        self._hvac.hub.sensors.average_temp_outdoors.value >= self._hvac.hub.options.heating_options.summer_temp,
                        self._hvac.hub.sensors.set_temp_indoors.preset != HvacPresets.Away,
                    ]
                )

    def _vent_boost_night_cooling(self) -> bool:
        return all(
                    [
                        self._hvac.hub.sensors.get_tempdiff_in_out() > 4,
                        self._hvac.hub.sensors.average_temp_outdoors.value >= self._hvac.hub.options.heating_options.summer_temp,
                        datetime.now().hour in self._hvac.hub.options.heating_options.night_hours,
                        self._hvac.hub.sensors.set_temp_indoors.preset != HvacPresets.Away,
                    ]
                )


    def _vent_boost_low_dm(self) -> bool:
        return all(
                    [
                        self._hvac.hvac_dm <= self._hvac.hub.options.heating_options.low_degree_minutes,
                        self._hvac.hub.sensors.average_temp_outdoors.value >= self._hvac.hub.options.heating_options.very_cold_temp,
                    ]
                )

    def _vent_boost_start(self, msg) -> None:
        if not self._current_vent_state:
            _LOGGER.debug(msg)
            self._wait_timer_boost.update()
            self._current_vent_state = True
            self._hvac.hub.observer.broadcast("update operation")