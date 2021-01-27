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

Supported features:
- Measurement setup: frequency sweep, data points, etc.
- Channel setup: parameter (S11, S12, ...), graph type, etc.
- Graph setup: scale, reference, offset
- Data transfer: channel data, screen bitmap, S2P file
