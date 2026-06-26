import sys
from pathlib import Path

# Allow importing the integration package without installation
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components" / "tr7_exalus_local"))

try:
    import pytest_homeassistant_custom_component  # noqa: F401
    pytest_plugins = "pytest_homeassistant_custom_component"
except ImportError:
    pass  # HA fixtures (hass, enable_custom_integrations) unavailable — only unit tests will run
