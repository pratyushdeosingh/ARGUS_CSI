"""Dashboard isolation and reconnect replay use real ingestion and scoring events."""
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.storage import ArgusStore


def test_session_filtered_history_and_replay(monkeypatch):
    monkeypatch.setenv("ARGUS_DETECTOR_MODE", "fixture")
    payload = dict(transaction_id="SYN-dashboard-00001", timestamp="2026-10-25T00:00:00Z", source_account="SYN-a-A001", destination_account="SYN-a-A002", amount=2500, currency="INR", device_id="SYN-device", ip_address="192.0.2.1", status="completed")
    with TestClient(app) as client:
        with client.websocket_connect('/ws/transactions') as socket:
            assert socket.receive_json()['event_type'] == 'connection.established'
            assert client.post('/api/transactions?session_id=dashboard-a', json=payload).status_code == 201
            received = socket.receive_json()
            assert received['session_id'] == 'dashboard-a'
            assert received['event_type'] == 'transaction.received'
        history = client.get('/api/transactions?session_id=dashboard-a').json()
        assert len(history) == 1
        assert client.get('/api/transactions?session_id=dashboard-b').json() == []
        events = client.get('/api/transaction-events?session_id=dashboard-a').json()
        types = {event['event_type'] for event in events}
        assert 'transaction.received' in types
        assert 'transaction.scored' in types or 'transaction.analysis_failed' in types
        assert 'transaction.scam_scored' in types or 'transaction.scam_scoring_failed' in types
        assert all(event['session_id'] == 'dashboard-a' for event in events)
        assert client.get('/api/transaction-events?session_id=dashboard-b').json() == []
        assert client.post('/api/transactions?session_id=dashboard-a', json=payload).status_code == 200
        assert client.get('/api/transaction-events?session_id=dashboard-a').json() == events
        assert len(client.get('/api/transactions').json()) == 1


def test_replay_is_bounded_and_ordered(tmp_path):
    store = ArgusStore(tmp_path / 'events.db')
    for i in range(5):
        event = dict(event_id=str(i), event_type='transaction.scored', data={'transaction_id':str(i)})
        store.save_stream_event('a', event)
        store.save_stream_event('a', event)
    assert [event['event_id'] for event in store.list_stream_events('a', 2)] == ['3', '4']
    assert store.list_stream_events('b') == []
