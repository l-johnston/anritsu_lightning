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

Supported features:
- Measurement setup: frequency sweep, data points, etc.
- Channel setup: parameter (S11, S12, ...), graph type, etc.
- Graph setup: scale, reference, offset
- Data transfer: channel data, screen bitmap, S2P file
