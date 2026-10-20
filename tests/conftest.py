"""Load integration modules without requiring a Home Assistant installation."""

from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).parents[1]
CUSTOM_COMPONENTS = ROOT / "custom_components"
DOMAIN_PACKAGE = CUSTOM_COMPONENTS / "hiveos_monitor"

custom_components = ModuleType("custom_components")
custom_components.__path__ = [str(CUSTOM_COMPONENTS)]
sys.modules.setdefault("custom_components", custom_components)

domain = ModuleType("custom_components.hiveos_monitor")
domain.__path__ = [str(DOMAIN_PACKAGE)]
sys.modules.setdefault("custom_components.hiveos_monitor", domain)
