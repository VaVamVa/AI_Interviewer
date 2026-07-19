from enum import Enum, auto


class AppState(Enum):
    IDLE         = auto()
    CONFIG_PANEL = auto()
    INITIALIZING = auto()
    SPEAKING     = auto()
    LISTENING    = auto()
    RECORDING    = auto()
    PROCESSING   = auto()
    ENDING       = auto()
