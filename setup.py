"""Setuptools install script"""
from setuptools import setup, find_packages


def get_readme():
    """Get readme contents"""
    with open("README.md") as f:
        return f.read()


def get_version():
    """Get the version number"""
    with open("anritsu_lightning/version.py") as f:
        lines = f.readlines()
    line = ""
    for line in lines:
        if line.startswith("__version__"):
            break
    version = [s.strip().strip('"') for s in line.split("=")][1]
    return version


setup(
    name="anritsu_lightning",
    version=get_version(),
    author="Lee Johnston",
    author_email="lee.johnston.100@gmail.com",
    description="Communication with Anritsu Lightning VNA",
    long_description=get_readme(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Science/Research",
    ],
    url="https://github.com/l-johnston/anritsu_lightning",
    install_requires=["pyvisa", "numpy"],
)
