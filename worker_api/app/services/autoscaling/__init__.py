"""
FluxVPN Auto-scaling Service

Provides automatic scaling of protocol instances based on:
- Connection load
- Health metrics
- Time-based patterns
"""

from .autoscaler import AutoScaler, ScalingAction, ScalingRule

__all__ = ["AutoScaler", "ScalingRule", "ScalingAction"]
