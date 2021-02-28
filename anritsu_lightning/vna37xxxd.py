"""Lightning 37xxxD series VNA"""
from functools import wraps
from datetime import datetime
from time import sleep
import asyncio
import itertools
from dataclasses import dataclass
import pyvisa
import numpy as np
from anritsu_lightning.common import InstrumentBase, get_idn, Subsystem, Error


@dataclass
class State:
    """Signal for controlling asyncio tasks"""

    running: bool = False


def validate(func):
    """Decorator to check for error when setting a parameter"""

    @wraps(func)
    def inner(*args, **kwargs):
        # pylint:disable=protected-access
        self = args[0]
        self._visa.write("*CLS;*ESE 60")
        func(*args, **kwargs)
        # need some delay before reading stb to avoid race condition
        # empirically determined >= 75 ms
        sleep(0.1)  # s
        if self._visa.stb & 32:
            esr = self._visa.query("*ESR?")
            raise Error(f"ESR: {esr} = " + self._visa.query("OGE"))
        self._visa.write("*ESE 0")

    return inner


DISPLAYMODES = {
    "1": "single channel",
    "single channel": "DSP",
    "13": "dual channels 1 & 3",
    "dual channels 1 & 3": "D13",
    "24": "dual channels 2 & 4",
    "dual channels 2 & 4": "D24",
    "4": "all four channels",
    "all four channels": "D14",
}
CRTSTATES = {"0": "OFF", "OFF": "BC0", "1": "ON", "ON": "BC1"}

SWEEPMODES = {"1": "hold - continue", "2": "hold - restart", "3": "single sweep - hold"}


class Lightning(InstrumentBase):
    """Anritsu Lightning 37xxxD series VNA

    Parameters
    ----------
    visa : pyvisa.resources.Resource
    """

    def __init__(self, visa):
        super().__init__(visa)
        self._visa.write("*CLS;*ESE 0")
        self._visa.read_termination = "\n"
        self._idn = get_idn(visa)
        self.measurement_setup = MeasurementSetup(self)
        self.ch1 = Channel(self, 1)
        self.ch2 = Channel(self, 2)
        self.ch3 = Channel(self, 3)
        self.ch4 = Channel(self, 4)
        self._state = State()
        self.disk = Disk(self)

    @property
    def model(self):
        """Return model number

        Returns
        ----------
        model : str
        """
        return self._idn.model

    @property
    def serial_number(self):
        """Return serial number

        Returns
        -------
        serial_number : str
        """
        return self._idn.serial_number

    @property
    def firmware_version(self):
        """Return firmware version

        Returns
        -------
        firmware_version : str
        """
        return self._idn.firmware_version

    def __repr__(self):
        return f"<Anritsu {self.model} at {self._visa.resource_name}>"

    def set_time(self):
        """Set the date and time to the controller's local time"""
        now = datetime.now()
        year = now.year
        month = now.month
        day = now.day
        hour = now.hour
        minute = now.minute
        second = now.second
        minute = int(np.round(minute + second / 60))
        self._visa.write(f"TIME {hour}, {minute}")
        self._visa.write(f"DATE {month}, {day}, {year}")

    @property
    def time(self):
        """Return the VNA's clock time

        Returns
        -------
        time : datetime.datetime
        """
        hour, minute = self._visa.query("TIME?").split(",")
        month, day, year = self._visa.query("DATE?").split(",")
        params = map(int, [year, month, day, hour, minute])
        return datetime(*params)

    def _query(self, value):
        return self._visa.query(value)

    def _write(self, value):
        self._visa.write(value)

    @property
    def _stb(self):
        return self._visa.stb

    @property
    def active_channel(self):
        """Active channel

        Parameters
        ----------
        value : int {1, 2, 3, 4}
        """
        return int(self._visa.query("CHX?"))

    @active_channel.setter
    @validate
    def active_channel(self, value):
        self._visa.write(f"CH{value}")

    @property
    def display_mode(self):
        """Display mode

        Parameters
        ----------
        value : str {'single channel', 'dual channels 1 & 3',
            'overlay dual channels 1 & 3', 'dual channels 2 & 4',
            'overlay dual channels 2 & 4', 'all four channels'}
        """
        dsp = self._visa.query("DSP?")
        return DISPLAYMODES[dsp]

    @display_mode.setter
    @validate
    def display_mode(self, value):
        dsp = DISPLAYMODES[value]
        self._visa.write(f"{dsp}")

    @property
    def crt(self):
        """CRT screen state

        Parameters
        ----------
        value : str {'ON', 'OFF'}
        """
        bcx = self._visa.query("BCX?")
        return CRTSTATES[bcx]

    @crt.setter
    @validate
    def crt(self, value):
        self._visa.write(CRTSTATES[value])

    def reset(self):
        """Reset instrument"""
        original_timeout = self._visa.timeout
        # increase timeout to allow for reset operation to complete
        self._visa.timeout = 10000  # ms
        self._visa.query("*RST;*OPC?")
        self._visa.timeout = original_timeout

    async def _show_spinner(self):
        # show an in-progress spinner during task
        glyph = itertools.cycle(["-", "\\", "|", "/"])
        while self._state.running:
            print(next(glyph), end="")
            print("\r", end="")
            await asyncio.sleep(0.5)
        print("\r \r", end="")
        return 0

    async def _sweep(self):
        # perform sweep
        try:
            original_hld = bool(int(self._visa.query("HLD?")))
            self._visa.write("*CLS;HLD;IEM 8;TRS;WFS")
            while not self._visa.stb and 128:
                await asyncio.sleep(1)
            self._state.running = False
            oeb = int(self._visa.query("OEB"))
            sweep_complete = bool(oeb & 8)
            ctn = "" if original_hld else "CTN"
            self._visa.write(f"IEM 0;{ctn}")
            return 0 if sweep_complete else 1
        except asyncio.CancelledError:
            pass
        except pyvisa.VisaIOError as exc:
            if exc.abbreviation == "VI_ERROR_TMO":
                raise TimeoutError(
                    "Acquisition timed out due to loss of communication"
                ) from None
            raise

    async def _start_task(self, timeout):
        self._state.running = True
        task = asyncio.gather(self._show_spinner(), self._sweep())
        try:
            ret_value = await asyncio.wait_for(task, timeout)
        except asyncio.TimeoutError:
            raise TimeoutError("sweep timeout") from None
        else:
            return ret_value

    def get_s2p(self, previous=True, timeout=None):
        """Retrieve S-parameters in S2P file format

        Parameters
        ----------
        previous : bool
            Whether to read the existing data from previous sweep
        timeout : int
            When previous=False, amount of time allowed for sweep to complete

        Returns
        -------
        s2p : str
            entire s2p file as one string
        """
        if not previous:
            asyncio.run(self._start_task(timeout))
        self._visa.write("OS2P")
        # need a delay to avoid race condition (*OPC? doesn't work)
        # empirically determined >= 0.75 s
        sleep(1)
        s2p = self._read_arbitraryblock().decode("ascii")
        return s2p

    def get_bitmap(self, color="color"):
        """Retrieve screen bitmap image

        Parameters
        ----------
        color : str {'black', 'color', 'true'}

        Returns
        -------
        bitmap : bytes
        """
        colorcode = color.upper()[0]
        self._visa.write(f"BMP{colorcode};WIDE;OBMP")
        bmp = self._read_arbitraryblock()
        return bmp

    @property
    def sweep_mode(self):
        """Return sweep mode"""
        hldx = self._visa.query("HLDX?")
        return SWEEPMODES[hldx]

    @property
    def sweep_state(self):
        """Sweep state

        Parameters
        ----------
        value : str {'hold', 'continue'}
        """
        hld = bool(int(self._visa.query("HLD?")))
        return "hold" if hld else "continue"

    @sweep_state.setter
    @validate
    def sweep_state(self, value):
        sweep = "HLD" if value == "hold" else "CTN"
        self._visa.write(f"{sweep}")

    @staticmethod
    def _parse_chs(channel):
        if ":" in channel:
            channels = list(range(*map(int, channel.split(":"))))
            channels.append(channel[-1] + 1)
        else:
            channels = list(map(int, channel.split(",")))
        return channels

    def read(self, channel, data_status, previous=True):
        """Read data from given channel

        Parameters
        ----------
        channel : int {1, 2, 3, 4} or str
            if str, e.g. {'1:4', '1, 3', ...}
        data_status : str {'raw', 'corrected', 'final'}
            raw data is uncorrected re/im and returned as np.complex128
            corrected is re/im and returned as np.complex128
            final is based on front panel setup
        previous : bool

        Returns
        -------
        dataset : np.ndarray
        """
        data_status = data_status.upper()[0]
        channels = [channel] if isinstance(channel, int) else self._parse_chs(channel)
        if not previous:
            pass
        dataset = []
        original_active_ch = self.active_channel
        for ch in channels:
            self.active_channel = ch
            self._visa.write(f"FMB;LSB;O{data_status}D")
            data = self._visa.read_binary_values(datatype="d", container=np.ndarray)
            if data_status in ["R", "C"]:
                rows = data.size // 2
                data = np.array(list(map(lambda x: complex(*x), data.reshape(rows, 2))))
            dataset.append(data)
        dataset = dataset if len(dataset) > 1 else dataset[0]
        self.active_channel = original_active_ch
        return dataset

    @property
    def sweep_frequencies(self):
        """Return sweep frequencies

        Returns
        -------
        frequencies : np.ndarray in hertz
        """
        self._visa.write("FMB;LSB;OFV")
        return self._visa.read_binary_values(datatype="d", container=np.ndarray)

    @property
    def averaging(self):
        """sweep-by-sweep averaging

        Parameters
        ----------
        value : int
            number of sweep-by-sweep averages (set to 1 to turn off averaging)

        Returns
        -------
        count : int
        """
        return int(self._visa.query("AVG?"))

    @averaging.setter
    @validate
    def averaging(self, value):
        if value > 1:
            self._visa.write(f"SWAVG;AVG {value}")
        else:
            self._visa.write("AOF")

    @property
    def avg_count(self):
        """Return current averaging sweep count"""
        return int(self._visa.query("AVGCNT?"))

    @property
    def smoothing(self):
        """smoothing as a percent of sweep

        Parameters
        ----------
        value : float
            amount of smoothing as a percent of sweep time (set to 0 to turn off)

        Returns
        -------
        value : float
        """
        return float(self._visa.query("SON?"))

    @smoothing.setter
    @validate
    def smoothing(self, value):
        if value > 0:
            self._visa.write(f"SON {value}")
        else:
            self._visa.write("SOF")


class MeasurementSetup(Subsystem, kind="MeasurementSetup"):
    """Measurement setup"""

    @property
    def start(self):
        """Sweep start frequency

        Parameters
        ----------
        value : str, float in hertz
            As str, e.g. '1 GHz'
            As float, e.g. 1.0e9

        Returns
        -------
        value : float in hertz
        """
        return float(self._visa.query("SRT?"))

    @start.setter
    @validate
    def start(self, value):
        self._visa.write(f"SRT {value}")

    @property
    def stop(self):
        """Sweep stop frequency

        Parameters
        ----------
        value : str, float in hertz
            As str, e.g. '1 GHz'
            As float, e.g. 1.0e9

        Returns
        -------
        value : float in hertz
        """
        return float(self._visa.query("STP?"))

    @stop.setter
    @validate
    def stop(self, value):
        self._visa.write(f"STP {value}")

    @property
    def center(self):
        """Sweep center frequency

        Parameters
        ----------
        value : str, float in hertz
            As str, e.g. '1 GHz'
            As float, e.g. 1.0e9

        Returns
        -------
        value : float in hertz
        """
        return float(self._visa.query("CNTR?"))

    @center.setter
    @validate
    def center(self, value):
        self._visa.write(f"CNTR {value}")

    @property
    def span(self):
        """Sweep frequency span

        Parameters
        ----------
        value : str, float in hertz
            As str, e.g. '1 GHz'
            As float, e.g. 1.0e9

        Returns
        -------
        value : float in hertz
        """
        return float(self._visa.query("SPAN?"))

    @span.setter
    @validate
    def span(self, value):
        self._visa.write(f"SPAN {value}")

    @property
    def data_points(self):
        """Number of data points in the sweep

        Parameters
        ----------
        value : int {101, 201, 401, 801, 1601}
        """
        return int(self._visa.query("ONP"))

    @data_points.setter
    @validate
    def data_points(self, value):
        self._visa.write(f"NP{value}")


GRAPHTYPES = {
    "1": "log magnitude",
    "log magnitude": "MAG",
    "2": "phase",
    "phase": "PHA",
    "3": "log magnitude and phase",
    "log magnitude and phase": "MPH",
    "4": "smith chart",
    "smith chart": "SMI",
}

REFPOSITIONS = {"0": "bottom", "4": "mid", "8": "top"}


class Channel(Subsystem, kind="Channel"):
    """Channel subsystem"""

    def __init__(self, instr, channel):
        super().__init__(instr)
        self._ch = channel

    @property
    def parameter(self):
        """S-parameter

        Parameters
        ----------
        value : str {'S11', 'S12', 'S21', 'S22'}
        """
        return "S" + self._visa.query(f"CH{self._ch};SXX?")

    @parameter.setter
    @validate
    def parameter(self, value):
        self._visa.write(f"CH{self._ch};{value}")

    @property
    def graph_type(self):
        """Graph type

        Parameters
        ----------
        value : str {'log magnitude', 'log magnitude and phase', 'smith chart'}
        """
        grf = self._visa.query(f"CH{self._ch};GRF?")
        return GRAPHTYPES[grf]

    @graph_type.setter
    @validate
    def graph_type(self, value):
        self._visa.write(f"CH{self._ch};{GRAPHTYPES[value]}")

    @property
    def graph_scale(self):
        """Graph scale per division

        Parameters
        ----------
        value : float or 2-tuple of float
            For 'log magnitude and phase' use 2-tuple
        """
        top_scale = float(self._visa.query(f"CH{self._ch};SCL?"))
        grf = self._visa.query(f"CH{self._ch};GRF?")
        if GRAPHTYPES[grf] == "log magnitude and phase":
            bottom_scale = float(self._visa.query(f"CH{self._ch};SCL2?"))
            result = (top_scale, bottom_scale)
        else:
            result = top_scale
        return result

    @graph_scale.setter
    @validate
    def graph_scale(self, value):
        if isinstance(value, tuple):
            top_scale, bottom_scale = value
            self._visa.write(f"CH{self._ch};SCL {top_scale}")
            self._visa.write(f"SCL2 {bottom_scale}")
        else:
            self._visa.write(f"CH{self._ch};SCL {value}")

    @property
    def reference(self):
        """Reference value

        Parameters
        ----------
        value : float or 2-tuple of float
            For 'log magnitude and phase' use 2-tuple
        """
        top_ref = float(self._visa.query(f"CH{self._ch};OFF?"))
        grf = self._visa.query("GRF?")
        if GRAPHTYPES[grf] == "log magnitude and phase":
            bottom_ref = float(self._visa.query("OFF2?"))
            result = (top_ref, bottom_ref)
        else:
            result = top_ref
        return result

    @reference.setter
    @validate
    def reference(self, value):
        if isinstance(value, tuple):
            top_ref, bottom_ref = value
            self._visa.write(f"CH{self._ch};OFF {top_ref}")
            self._visa.write(f"OFF2 {bottom_ref}")
        else:
            self._visa.write(f"CH{self._ch};OFF {value}")

    @property
    def ref_position(self):
        """Reference position (graticule)

        Parameters
        ----------
        value : str {'top', 'mid', 'bottom'} or 2-tuple of str
            For 'log magnitude and phase' use 2-tuple
        """
        top_refline = self._visa.query(f"CH{self._ch};REF?")
        top_refpos = REFPOSITIONS[top_refline]
        grf = self._visa.query("GRF?")
        if GRAPHTYPES[grf] == "log magnitude and phase":
            bottom_refline = self._visa.query("REF2?")
            bottom_refpos = REFPOSITIONS[bottom_refline]
            result = (top_refpos, bottom_refpos)
        else:
            result = top_refpos
        return result

    def __dir__(self):
        attrs = super().__dir__()
        grf = self._visa.query(f"CH{self._ch};GRF?")
        if GRAPHTYPES[grf] == "smith chart":
            attrs.remove("reference")
            attrs.remove("ref_position")
        return attrs


class Disk(Subsystem, kind="Disk"):
    """Disk subsystem"""

    @property
    def current_directory(self):
        """Current working directory"""
        return self._visa.query("CWD?")

    def change_directory(self, directory):
        """Change directory

        Parameters
        ----------
        dir : str {'A:\\', 'C:\\', '<sub directory>'}
        """
        self._visa.write("*ESE 1")
        original_timeout = self._visa.timeout
        self._visa.timeout = 10000  # ms
        if directory in ["A:\\", "C:\\"]:
            self._visa.query(f"{directory[0]}DRIVE;*OPC?")
        else:
            self._visa.query(f"CD '{directory}';*OPC?")
        self._visa.write("*ESE 0")
        self._visa.timeout = original_timeout

    def listdir(self):
        """Return list of files in the current directory"""
        self._visa.write("DIR")
        listing = self._read_arbitraryblock().decode("ascii").split(",")
        files = []
        for line in listing[1:-1]:
            name, extension = line.split()[:2]
            files.append(f"{name}.{extension}")
        return files

    def read(self, file):
        """Read file and return as bytes object"""
        self._visa.write(f"DISKRD '{file}';*ESE 1;*OPC")
        while not self._visa.stb & 32:
            pass
        contents = self._read_arbitraryblock()
        self._visa.write("*ESE 0")
        return contents

    def load_calkit(self, from_floppy=True, file=None):
        """Load cal kit info

        Parameters
        ----------
        from_floppy : bool
            If false, provide file path
        file : str
            file path to 'KIT_INFO.<xxx>'
        """
        if from_floppy:
            original_timeout = self._visa.timeout
            # increase timeout to allow for floppy disk op
            self._visa.timeout = 20000  # ms
            self._visa.query("LKT;*OPC?")
            self._visa.timeout = original_timeout
        else:
            with open(file, "rb") as f:
                extension = file.split(".")[-1]
                kitinfo = self._format_arbitraryblock(f.read())
            payload = bytes(f"IKIT '{extension}', ".encode("ascii")) + kitinfo + b"\n"
            self._visa.write_raw(payload)
