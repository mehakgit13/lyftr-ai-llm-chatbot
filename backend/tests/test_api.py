import os, tempfile
from fastapi.testclient import TestClient

# Use a temporary SQLite DB and mock inference before importing the application.
tmp = tempfile.NamedTemporaryFile(delete=False)
os.environ["DATABASE_URL"] = "sqlite:///" + tmp.name
os.environ["MOCK_LLM"] = "true"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"
os.environ["LLM_API_KEYS"] = ""
from app import main
client = TestClient(main.app)

def test_health_contract():
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["cache_enabled"] is True

def test_chat_and_cache():
    main._RESPONSE_CACHE.clear()
    first = client.post('/chat', json={"session_id":"test-a", "message":"Hello"})
    assert first.status_code == 200
    assert first.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    second = client.post('/chat', json={"session_id":"test-b", "message":"Hello"})
    assert second.status_code == 200
    assert second.json()["reply"] == first.json()["reply"]
    assert second.json()["metadata"]["resolution_source"] == "LLM_CACHE"
    assert second.json()["metadata"]["key_id"] is None

def test_fallback_and_all_keys_fail():
    main._RESPONSE_CACHE.clear()
    r = client.post('/chat', json={"session_id":"fallback", "message":"Unique question"}, headers={"X-Simulate-Failure":"key_1=429"})
    assert r.status_code == 200
    assert r.json()["metadata"]["key_id"] == "key_2"
    assert r.json()["metadata"]["fallback_attempts"] == 1
    main._RESPONSE_CACHE.clear()
    r = client.post('/chat', json={"session_id":"failed", "message":"Another unique question"}, headers={"X-Simulate-Failure":"*=429"})
    assert r.status_code == 503
    assert r.json()["detail"] == "all providers unavailable"
    # A request that exhausts every provider must not create a session or messages.
    assert client.get('/sessions/failed/messages').status_code == 404

def test_history_and_unknown_session():
    r = client.post('/chat', json={"session_id":"history-1", "message":"Remember this"})
    assert r.status_code == 200
    h = client.get('/sessions/history-1/messages')
    assert h.status_code == 200
    assert [m["role"] for m in h.json()["messages"]] == ["user", "assistant"]
    assert client.get('/sessions/no-such-session/messages').status_code == 404

def test_validation():
    assert client.post('/chat', json={"session_id":"x", "message":"  "}).status_code == 422
    assert client.post('/chat', json={"session_id":"x", "message":"a"*4001}).status_code == 422
