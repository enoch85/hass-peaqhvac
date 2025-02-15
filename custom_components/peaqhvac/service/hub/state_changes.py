import logging
import time

from peaqevcore.common.wait_timer import WaitTimer

_LOGGER = logging.getLogger(__name__)


class StateChanges:


    def __init__(self, hub, hass):
        self._hub = hub
        self._hass = hass
        self.latest_nordpool_update = WaitTimer(timeout=300)

    async def async_initialize_values(self):
        for t in self._hub.trackerentities:
            retval = self._hass.states.get(t)
            if retval is not None:
                await self.async_update_sensor(entity=t, value=retval.state)

    async def async_update_sensor(self, entity, value):
        if entity in self._hub.options.indoor_tempsensors:
            await self._hub.sensors.average_temp_indoors.async_update_values(
                entity=entity, value=value
            )
            await self._hub.sensors.temp_trend_indoors.async_add_reading(
                val=self._hub.sensors.average_temp_indoors.value, t=time.time()
            )
        elif entity in self._hub.options.outdoor_tempsensors:
            await self._hub.sensors.average_temp_outdoors.async_update_values(
                entity=entity, value=value
            )
            await self._hub.sensors.temp_trend_outdoors.async_add_reading(
                val=self._hub.sensors.average_temp_outdoors.value, t=time.time()
            )
        await self._hass.async_add_executor_job(
            self._hub.prognosis.get_hvac_prognosis,
            self._hub.sensors.average_temp_outdoors.value,
        )

        if (
            entity == self._hub.nordpool.nordpool_entity
            or self.latest_nordpool_update.is_timeout()
        ):
            await self._hub.nordpool.async_update_nordpool()
            await self._hass.async_add_executor_job(
                self._hub.prognosis.update_weather_prognosis
            )
            self.latest_nordpool_update.update()
        await self._hub.hvac.async_update_hvac()
