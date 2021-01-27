"""Common definitions"""
from collections import namedtuple

IDN = namedtuple("IDN", ["manufacturer", "model", "serial_number", "firmware_version"])


def get_idn(visa):
    """Get IDN"""
    idn = visa.query("*IDN?").strip(":\n").split(",")
    return IDN(*idn)


class Error(Exception):
    """Error class for Lightning"""


class InstrumentBase:
    """Instrument base class

    Attributes:
        visa (pyvisa.resources.Resource): pyvisa resource
    """

    def __init__(self, visa):
        self._visa = visa

    def __setattr__(self, name, value):
        if hasattr(self, name) and isinstance(getattr(self, name), InstrumentBase):
            raise AttributeError(f"can't set '{name}'")
        if hasattr(self.__class__, name):
            prop = getattr(self.__class__, name)
            try:
                prop.fset(self, value)
            except TypeError:
                raise AttributeError(f"can't set '{name}'") from None
        else:
            self.__dict__[name] = value

    def __repr__(self):
        raise NotImplementedError

    def __dir__(self):
        inst_attr = list(filter(lambda k: not k.startswith("_"), self.__dict__.keys()))
        cls_attr = list(filter(lambda k: not k.startswith("_"), dir(self.__class__)))
        return inst_attr + cls_attr

    def _read_arbitraryblock(self):
        # return arbitrary block as bytes object
        # arbitrary block format: b'#<n><blk_size><data>'
        ch = self._visa.read_bytes(1)
        if ch != b"#":
            raise TypeError("not an arbitrary block of data")
        n = int(self._visa.read_bytes(1))
        blk_size = int(self._visa.read_bytes(n))
        # increase VISA timeout
        original_timeout = self._visa.timeout
        self._visa.timeout = 10000  # ms
        data = self._visa.read_bytes(blk_size)
        self._visa.read_bytes(1)  # new line termination
        self._visa.timeout = original_timeout
        return data

    @staticmethod
    def _format_arbitraryblock(data):
        # format data (bytes) as arbitrary block
        blk_size = bytes(str(len(data)).encode("ascii"))
        n = bytes(str(len(blk_size)).encode("ascii"))
        return b"#" + n + blk_size + data


class Subsystem(InstrumentBase):
    """Base class for a specific measurement function

    Parameters
    ----------
        instr : Lightning
    """

    _kind = "Instrument"

    def __init__(self, instr):
        super().__init__(instr._visa)
        self._instr = instr

    def __init_subclass__(cls, kind):
        cls._kind = kind

    def __get__(self, instance, owner=None):
        return self

    def __repr__(self):
        return f"<{self._instr.model} {self._kind}>"
