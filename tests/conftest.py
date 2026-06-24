import pytest

from mcp_server.models.blender import BlenderCommand, BlenderError, BlenderResponse
from mcp_server.state.scene_state import reset


@pytest.fixture(autouse=True)
def clean_state():
    reset()
    yield
    reset()


class FakeBlenderClient:
    def __init__(self, response: BlenderResponse) -> None:
        self._response = response
        self.last_command: BlenderCommand | None = None

    async def send(self, command: BlenderCommand) -> BlenderResponse:
        self.last_command = command
        return self._response


@pytest.fixture
def make_client():
    def _factory(response: BlenderResponse) -> FakeBlenderClient:
        return FakeBlenderClient(response)
    return _factory


@pytest.fixture
def disconnected_client() -> FakeBlenderClient:
    return FakeBlenderClient(
        BlenderResponse(
            success=False,
            error=BlenderError(
                code="BLENDER_NOT_CONNECTED",
                message="无法连接到 Blender Addon",
            ),
        )
    )
