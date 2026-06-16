"""Build a redistributable wheel for the `fpm` package.

The package ships a *prebuilt* C++ extension (fpm/fpm.*.pyd) plus the OpenCV runtime
DLLs it needs (fpm/_libs/*.dll). Because we do not compile here, we force a
platform-specific (non-pure) wheel so the tags become e.g. cp312-cp312-win_amd64:
that wheel is only valid on the Python version / OS / arch it was built with — which
is exactly what we want for a prebuilt binary.

Build (from this folder, using the target Python 3.12 x64):

    python -m pip install build
    python -m build --wheel
    # -> dist/fpm-0.1.0-cp312-cp312-win_amd64.whl
"""
from setuptools import setup
from setuptools.dist import Distribution


class BinaryDistribution(Distribution):
    """Mark the distribution as non-pure so the wheel gets platform + abi tags."""

    def has_ext_modules(self):  # noqa: D401
        return True

    def is_pure(self):
        return False


setup(distclass=BinaryDistribution)
