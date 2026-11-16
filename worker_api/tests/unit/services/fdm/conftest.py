"""
Pytest configuration for FDM DNS client tests (no database required)
"""

import pytest


def pytest_configure(config):
    """
    Configure pytest to skip database fixtures for FDM tests
    """
    # Mark all tests in this directory as not requiring database
    config.addinivalue_line("markers", "nodatabase: Tests that don't require database")
