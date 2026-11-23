"""Minimal PySide6/QtCore startup check for CPU compatibility CI."""
from PySide6 import QtCore

print(f"QtCore import OK; Qt version: {QtCore.qVersion()}")
