"""Python interface to the Anritsu Lightning 37xxxD VNA"""
import pyvisa
from anritsu_lightning.version import __version__
from anritsu_lightning.common import get_idn
from anritsu_lightning.vna37xxxd import Lightning

__all__ = ["CommChannel"]


class CommChannel:
    """Connect to an Anritsu power meter using VISA

    Attributes
    ----------
        address : int
            instrument's GPIB address, e.g. 6
        controller : int
            GPIB controller primary address, e.g. 0

    Returns:
        CommChannel or Lightning
    """

    def __init__(self, address=6, controller=0):
        self._address = address
        self._controller = controller
        self._rm = pyvisa.ResourceManager()
        self._visa = self._rm.open_resource(f"GPIB{controller}::{address}::INSTR")
        self._visa.read_termination = "\n"

    def __enter__(self):
        idn = get_idn(self._visa)
        if idn.manufacturer.lower() != "anritsu":
            raise ValueError(
                f"Device at {self._address} is a not an Anritsu instrument"
            )
        return Lightning(self._visa)

    def __exit__(self, exc_type, exc_value, exc_tb):
        # enable local front panel control
        self._visa.write("RTL")
        self._visa.close()
        self._rm.close()

    def get_instrument(self):
        """Return the PowerMeter instrument object"""
        return self.__enter__()

    def close(self):
        """Close the CommChannel"""
        self.__exit__(None, None, None)


def __dir__():
    return ["CommChannel", "__version__"]
