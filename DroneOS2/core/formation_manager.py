from enum import Enum
import math
from typing import Tuple

class FormationType(str, Enum):
    LINE = "LINE"
    COLUMN = "COLUMN"
    V = "V"
    DIAMOND = "DIAMOND"
    SQUARE = "SQUARE"
    CIRCLE = "CIRCLE"
    ECHELON_LEFT = "ECHELON_LEFT"
    ECHELON_RIGHT = "ECHELON_RIGHT"
    GRID = "GRID"
    WEDGE = "WEDGE"

class FormationManager:
    """
    Computes spatial offsets for drones in a swarm to maintain a specific formation.
    The leader (index 0) is at (0, 0, 0). Offsets are given in relative (x, y, z) meters.
    X is forward, Y is right, Z is down.
    """
    def __init__(self):
        self.spacing: float = 5.0
        self.formation_type: FormationType = FormationType.V

    def set_formation(self, formation: FormationType, spacing: float = 5.0) -> None:
        self.formation_type = formation
        self.spacing = spacing

    def get_offset(self, my_index: int, total_drones: int) -> Tuple[float, float, float]:
        if my_index == 0:
            return (0.0, 0.0, 0.0)

        t = self.formation_type
        s = self.spacing

        if t == FormationType.LINE:
            sign = 1 if my_index % 2 != 0 else -1
            y_offset = sign * math.ceil(my_index / 2.0) * s
            return (0.0, y_offset, 0.0)

        elif t == FormationType.COLUMN:
            return (-my_index * s, 0.0, 0.0)

        elif t in (FormationType.V, FormationType.WEDGE):
            sign = 1 if my_index % 2 != 0 else -1
            tier = math.ceil(my_index / 2.0)
            return (-tier * s, sign * tier * s, 0.0)

        elif t == FormationType.ECHELON_LEFT:
            return (-my_index * s, -my_index * s, 0.0)

        elif t == FormationType.ECHELON_RIGHT:
            return (-my_index * s, my_index * s, 0.0)

        elif t == FormationType.CIRCLE:
            if total_drones > 1:
                angle_step = (2.0 * math.pi) / (total_drones - 1)
                angle = (my_index - 1) * angle_step
                return (s * math.cos(angle), s * math.sin(angle), 0.0)

        elif t == FormationType.DIAMOND:
            # Scale dynamically based on tiers, but simplified for now
            if total_drones == 2:
                return (-s, 0.0, 0.0) # Fallback to column for 2
            if my_index == 1: return (-s, s, 0.0)
            if my_index == 2: return (-s, -s, 0.0)
            if my_index == 3: return (-2.0 * s, 0.0, 0.0)
            # Default to trailing V if more than 4
            sign = 1 if my_index % 2 != 0 else -1
            tier = math.ceil(my_index / 2.0)
            return (-tier * s * 2, sign * s, 0.0)

        elif t == FormationType.SQUARE or t == FormationType.GRID:
            if total_drones == 2:
                return (0.0, s, 0.0) # Line for 2
            cols = math.ceil(math.sqrt(total_drones))
            row = my_index // cols
            col = my_index % cols
            return (-row * s, col * s, 0.0)
            
        return (0.0, 0.0, 0.0)
