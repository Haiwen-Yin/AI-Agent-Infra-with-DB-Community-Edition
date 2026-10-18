"""Activate only the explicitly selected database adapter."""
from .database_selection import activate_adapter
activate_adapter(__name__)
