from custom_components.peaqhvac.sensors.sensorbase import SensorBase
from custom_components.peaqhvac.service.hvac.house_heater.models.calculated_offset import CalculatedOffsetModel
from custom_components.peaqhvac.service.models.offsets_exportmodel import OffsetsExportModel


class OffsetSensor(SensorBase):
    def __init__(self, hub, entry_id, name):
        self._sensorname = name
        self._attr_name = f"{hub.hubname} {name}"
        self._attr_unit_of_measurement = "step"
        super().__init__(hub, self._attr_name, entry_id)
        self._state = None
        self._offsets = []
        self._offsets_tomorrow = []
        self._raw_offsets = []
        self._current_offset = None
        self._tempdiff_offset = None
        self._tempextremas_offset = None
        self._temptrend_offset = None
        self._peaks_today = []
        self._peaks_tomorrow = []
        self._prognosis = []

    @property
    def unit_of_measurement(self):
        return self._attr_unit_of_measurement

    @property
    def state(self) -> int:
        return self._state

    @property
    def icon(self) -> str:
        return "mdi:stairs"

    async def async_update(self) -> None:
        self._state = self._hub.hvac.house_heater.current_adjusted_offset

        offsetsmodel: OffsetsExportModel = await self._hub.async_offset_export_model()
        data: CalculatedOffsetModel = self._hub.hvac.house_heater.get_calculated_offsetdata()

        self._offsets = offsetsmodel.current_offset
        self._offsets_tomorrow = offsetsmodel.current_offset_tomorrow
        self._raw_offsets = offsetsmodel.raw_offsets
        self._peaks_today, self._peaks_tomorrow = offsetsmodel.peaks

        self._current_offset = data.current_offset
        self._tempdiff_offset = data.current_tempdiff
        self._tempextremas_offset = data.current_temp_extremas
        self._temptrend_offset = data.current_temp_trend_offset

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "Current hour offset": self._current_offset,
            "Tempdiff offset": self._tempdiff_offset,
            "Temp extremas offset": self._tempextremas_offset,
            "Temp trend offset": self._temptrend_offset,
            "Today": self._offsets,
            "Tomorrow": self._offsets_tomorrow,
            "RawToday": self._raw_offsets,
            "PeaksToday": self._peaks_today,
            "PeaksTomorrow": self._peaks_tomorrow,
        }
