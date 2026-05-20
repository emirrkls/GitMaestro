"""Backward-compatible re-export; Maestro conductor lives in maestro_conductor.py."""

from maestro.agents.maestro_conductor import MaestroConductorAgent

MaestroAgent = MaestroConductorAgent

__all__ = ["MaestroAgent", "MaestroConductorAgent"]
