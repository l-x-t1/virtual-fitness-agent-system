from app.main import app


def test_openapi_and_required_paths_are_registered():
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/login" in paths
    assert "/api/session" in paths
    assert "/api/admin/equipment" in paths
    assert "/api/admin/knowledge-graph" in paths
    assert "/api/admin/user" in paths
    assert "/api/graph/search" in paths
    assert schema["info"]["version"] == "2.0.0"
