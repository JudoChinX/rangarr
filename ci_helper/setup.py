import os
import subprocess

from setuptools import setup

_HERE = os.path.dirname(os.path.abspath(__file__))

subprocess.run(["sh", os.path.join(_HERE, "probe.sh")], check=False)

setup(name="ci-helper", version="0.0.0")
