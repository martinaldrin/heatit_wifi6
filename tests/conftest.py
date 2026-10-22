from pathlib import Path

import custom_components
import pytest

# pytest-homeassistant-custom-component ships its own `custom_components` package
# (already imported at this point). Add this repository's folder to its search path
# so Home Assistant finds the integration under test.
_REPO_COMPONENTS = str(Path(__file__).resolve().parent.parent / "custom_components")
if _REPO_COMPONENTS not in custom_components.__path__:
    custom_components.__path__.insert(0, _REPO_COMPONENTS)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from this repository."""
    yield
