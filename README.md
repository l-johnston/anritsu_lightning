![Build Status](https://github.com/l-johnston/anritsu_lightning/workflows/publish/badge.svg)
![PyPI](https://img.shields.io/pypi/v/anritsu_lightning)
# `anritsu_lightning`
Python interface to the Anritsu Lightning 37xxxD VNA

## Installation
```cmd
> pip install anritsu_lightning
```  

## Usage

```python
>>> from anritsu_lightning import CommChannel
>>> with CommChannel(address=6) as vna:
...     vna.ch3.parameter = "S21"
...     s21 = vna.read(channel=3, data_status="corrected")
>>> 
```

It is also possible to read the S-parameters in [Touchstone](https://ibis.org/connector/touchstone_spec11.pdf) SnP format.
```python
>>> from anritsu_lightning import CommChannel
>>> with CommChannel(address=6) as vna:
...     vna.measurement_setup.start = 40e6  # Hz
...     vna.measurement_setup.stop = 20e9  # Hz
...     vna.measurement_setup.data_points = 401
...     vna.ch1.parameter = "S11"
...     vna.ch1.graph_type = "log magnitude"
...     vna.ch1.graph_scale = 20.0  # dB/div
...     vna.ch2.parameter = "S12"
...     vna.ch3.parameter = "S21"
...     vna.ch3.graph_type = "log magnitude"
...     vna.ch3.graph_scale = 2.0  # dB/div
...     vna.ch4.parameter = "S22"
...     vna.display_mode = "dual channels 1 & 3"
...     with open(<file>, "wt") as f:
...         f.write(vna.get_s2p(previous=False))
>>>
```

It is also possible to use the markers to find the -3 dB point of a filter. In this
example, the VNA measured the -3 dB bandwidth of a Mini-Circuits VLF-1000+ low pass
filter with nominal specification of 1.3 GHz. The VNA was already setup to measure
S21 on channel 3 between 40 MHz and 5 GHz.

```python
In [1]: from anritsu_lightning import CommChannel
In [2]: cc = CommChannel(address=6)
In [3]: vna = cc.get_instrument()
In [4]: vna.markers.mode = "normal"
In [5]: vna.markers.enable([1, 2])
In [6]: vna.markers.set_active(1)
In [7]: vna.markers.set_xaxis_location(1, "40 MHz")
In [8]: vna.markers.delta_reference = 1
In [9]: vna.markers.set_active(2)
In [10]: bw = vna.markers.search("-3 dB", reference="delta reference", timeout=5000)
In [11]: print(f"{bw/1e9:.2f} GHz")
1.26 GHz
```

Supported features:
- Measurement setup: frequency sweep, data points, etc.
- Channel setup: parameter (S11, S12, ...), graph type, etc.
- Graph setup: scale, reference, offset
- Data transfer: channel data, screen bitmap, S2P file
- Markers
