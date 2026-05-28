def test_openapi_json_available(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"]
    assert schema["info"]["version"]


def test_openapi_lists_api_and_health_only(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert "/health" in paths
    assert "/api/v1/auth/login" in paths
    assert "/auth/login" not in paths
    assert "/dashboard" not in paths
    assert all(p.startswith("/api/v1") or p == "/health" for p in paths)


def test_openapi_session_cookie_security_scheme(client):
    schemes = client.get("/openapi.json").json()["components"]["securitySchemes"]
    assert "SessionCookie" in schemes
    assert schemes["SessionCookie"]["in"] == "cookie"
    assert schemes["SessionCookie"]["name"] == "session"


def test_openapi_login_is_public(client):
    login_op = client.get("/openapi.json").json()["paths"]["/api/v1/auth/login"]["post"]
    assert login_op.get("security") == []


def test_swagger_ui_available(client):
    assert client.get("/docs").status_code == 200
