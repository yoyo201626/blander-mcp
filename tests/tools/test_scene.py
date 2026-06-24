import pytest
from pydantic import ValidationError

from mcp_server.models.blender import BlenderResponse
from mcp_server.state.scene_state import get_state
from mcp_server.tools import scene


# ── 纯函数测试（无 I/O，无 fixture）────────────────────────────

class TestParseObjects:
    def test_parses_valid_objects(self):
        raw = [{"name": "Cube", "type": "MESH", "location": [1.0, 2.0, 3.0]}]
        result = scene._parse_objects(raw)
        assert len(result) == 1
        assert result[0].name == "Cube"
        assert result[0].location == [1.0, 2.0, 3.0]

    def test_raises_on_invalid_location_length(self):
        raw = [{"name": "Bad", "type": "MESH", "location": [0.0, 0.0]}]
        with pytest.raises(ValidationError):
            scene._parse_objects(raw)


class TestBuildDelta:
    def test_empty_by_default(self):
        delta = scene._build_delta()
        assert delta.removed == []
        assert delta.added == []

    def test_carries_removed_objects(self):
        delta = scene._build_delta(removed=["Cube", "Sphere"])
        assert delta.removed == ["Cube", "Sphere"]


# ── create ────────────────────────────────────────────────────

class TestCreate:
    async def test_returns_name_and_fps_on_success(self, make_client):
        client = make_client(BlenderResponse(
            success=True,
            result={"name": "TestScene", "fps": 30},
        ))
        result = await scene.create(client, name="TestScene", fps=30)
        assert result.success
        assert result.name == "TestScene"
        assert result.fps == 30

    async def test_sends_correct_tool_name(self, make_client):
        client = make_client(BlenderResponse(
            success=True,
            result={"name": "Scene", "fps": 24},
        ))
        await scene.create(client)
        assert client.last_command.tool == "scene.create"

    async def test_returns_failure_when_disconnected(self, disconnected_client):
        result = await scene.create(disconnected_client)
        assert not result.success
        assert result.error.code == "BLENDER_NOT_CONNECTED"


# ── clear ────────────────────────────────────────────────────

class TestClear:
    async def test_returns_removed_objects_in_delta(self, make_client):
        client = make_client(BlenderResponse(
            success=True,
            deleted_objects=["Cube", "Sphere"],
        ))
        result = await scene.clear(client)
        assert result.success
        assert result.scene_state_delta.removed == ["Cube", "Sphere"]

    async def test_resets_local_state_on_success(self, make_client):
        client = make_client(BlenderResponse(
            success=True,
            deleted_objects=[],
        ))
        await scene.clear(client)
        assert len(get_state().objects) == 0

    async def test_returns_failure_when_disconnected(self, disconnected_client):
        result = await scene.clear(disconnected_client)
        assert not result.success
        assert result.error is not None


# ── get_state_tool ────────────────────────────────────────────

class TestGetStateTool:
    async def test_syncs_objects_to_local_state(self, make_client):
        client = make_client(BlenderResponse(
            success=True,
            result={
                "objects": [
                    {"name": "Cube", "type": "MESH", "location": [0.0, 0.0, 0.0]},
                ],
                "frame_start": 1,
                "frame_end": 250,
                "frame_current": 10,
            },
        ))
        result = await scene.get_state_tool(client)
        assert result.success
        assert len(result.objects) == 1
        assert result.objects[0].name == "Cube"
        assert result.frame_current == 10
        assert "Cube" in get_state().objects

    async def test_syncs_frame_range(self, make_client):
        client = make_client(BlenderResponse(
            success=True,
            result={
                "objects": [],
                "frame_start": 5,
                "frame_end": 100,
                "frame_current": 50,
            },
        ))
        result = await scene.get_state_tool(client)
        assert result.frame_start == 5
        assert result.frame_end == 100

    async def test_returns_failure_when_disconnected(self, disconnected_client):
        result = await scene.get_state_tool(disconnected_client)
        assert not result.success
        assert result.error is not None

    async def test_raises_on_malformed_object_from_blender(self, make_client):
        client = make_client(BlenderResponse(
            success=True,
            result={
                "objects": [
                    {"name": "Bad", "type": "MESH", "location": [0.0]},
                ],
                "frame_start": 1,
                "frame_end": 250,
                "frame_current": 1,
            },
        ))
        with pytest.raises(ValidationError):
            await scene.get_state_tool(client)
