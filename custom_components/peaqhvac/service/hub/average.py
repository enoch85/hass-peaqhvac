import logging
import statistics as stat
from custom_components.peaqhvac.service.observer import Observer

_LOGGER = logging.getLogger(__name__)


class Average:
    def __init__(self, entities: list[str], observer: str = None, hub=None):
        self.listenerentities = entities
        self._value: float = 0.0
        self._median: float = 0.0
        self._max: float = 0.0
        self._min: float = 0.0
        self._all_values = []
        self._values = {}
        self._initialized_values = 0
        self._total_sensors = len(self.listenerentities)
        self._initialized_sensors = {}
        self._observer_message = observer
        self.hub = hub

        for i in self.listenerentities:
            self._values[i] = 999.0
            self._initialized_sensors[i] = False

    @property
    def initialized_percentage(self) -> float:
        try:
            return self._initialized_values / self._total_sensors
        except:
            return 0.0

    @property
    def sensorscount(self) -> int:
        return self._total_sensors

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, val) -> None:
        self._value = val
        self._broadcast_changes()

    @property
    def median(self) -> float:
        return self._median

    @property
    def max(self) -> float:
        return self._max

    @property
    def min(self) -> float:
        return self._min

    @property
    def all_values(self) -> list:
        return self._all_values

    def update_values(self, entity, value):
        try:
            floatval = float(value)
            if isinstance(floatval, (float, int)):
                if not self._initialized_sensors[entity]:
                    self._initialized_sensors[entity] = True
                    self._initialized_values += 1
                self._values[entity] = floatval
                self._create_values(self._values)
        except:
            _LOGGER.debug(f"unable to set average-val for {entity}: {value}")

    def _create_values(self, _values: dict):
        try:
            filtered_list = [i for i in _values.values() if i != 999.0]
            if self.initialized_percentage > 0.2:
                self._min = min(filtered_list)
                self._max = max(filtered_list)
                self.value = stat.mean(filtered_list)
                self._median = stat.median(filtered_list)
                self._all_values = filtered_list

            else:
                _LOGGER.debug(f"Unable to calculate average. Initialized sensors are: {self.initialized_percentage}")
                self.value = 0
        except:
            self.value = 0
            _LOGGER.debug("unable to set averagesensor")

    def _broadcast_changes(self):
        if self._observer_message is not None:
            self.hub.observer.broadcast(self._observer_message)
