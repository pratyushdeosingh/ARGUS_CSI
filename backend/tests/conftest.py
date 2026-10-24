"""Keep API tests independent of the developer's persistent demo database."""

import pytest

from backend.app.main import app
from backend.app.state import demo_state
from backend.app.storage import ArgusStore, get_argus_store


@pytest.fixture(autouse=True)
def isolated_api_state(tmp_path):
    demo_state.reset()
    store = ArgusStore(tmp_path / "api.db")
    app.dependency_overrides[get_argus_store] = lambda: store
    yield
    app.dependency_overrides.clear()
    demo_state.reset()
