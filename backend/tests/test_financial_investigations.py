"""Financial admission, isolation, replay, persistence and real-detector integration."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from backend.app.main import app
from backend.app.config import Settings
from backend.app.financial_cases import financial_finding
from backend.app.models import GraphSignal, Transaction
from backend.app.storage import ArgusStore, get_argus_store
# Exercise the actual graph/contextual risk engines behind a transport adapter.
from backend.tests.test_scam_streaming import mock_gateway, mock_graph_detector, isolated_manager

BASE = datetime(2026, 10, 25, tzinfo=timezone.utc)


def payment(n, source='a', target='b', amount=1000, seconds=0, status='completed', device='known'):
    return dict(transaction_id=f'PAY-{n}', timestamp=(BASE+timedelta(seconds=seconds)).isoformat(),
                source_account=source, destination_account=target, amount=amount,
                currency='INR', device_id=device, ip_address='192.0.2.1', status=status)


def finding(n, source, target, seconds=0):
    return dict(transaction_id=f'PAY-{n}', timestamp=(BASE+timedelta(seconds=seconds)).isoformat(),
                accounts=[source, target], risk_scores={'graph':90}, evidence=['Rapid forwarding'], signal_ids=[f'GRAPH-{n}'])


def test_admission_excludes_clean_pending_cancelled_and_unrelated_graph_scores():
    settings=Settings.from_env()
    tx=Transaction.model_validate(payment(1))
    graph=GraphSignal(signal_id='g', timestamp=BASE, risk_score=.95, anomaly_type='mule', suspicious_accounts=['a','b'], suspicious_transactions=['other'], related_ips=[], reasons=['Window evidence'])
    assert financial_finding(tx, graph, None, settings) is None
    graph.suspicious_transactions=['PAY-1']
    assert financial_finding(tx, graph, None, settings)['risk_scores']['graph']==95
    for status in ['pending','cancelled']:
        assert financial_finding(Transaction.model_validate(payment(1,status=status)),graph,None,settings) is None
    graph.risk_score=.2
    assert financial_finding(tx,graph,None,settings) is None


def test_components_are_grouped_idempotently_and_isolated_across_sessions(tmp_path):
    store=ArgusStore(tmp_path/'cases.db')
    assert store.record_financial_finding('one','mule',finding(1,'a','b'))==(None,False)
    first,changed=store.record_financial_finding('one','mule',finding(2,'b','c',1))
    assert changed and first.transaction_ids==['PAY-1','PAY-2']
    duplicate,changed=store.record_financial_finding('one','mule',finding(2,'b','c',1))
    assert not changed and duplicate==first
    # An unrelated cluster is a separate investigation, even in Mixed mode.
    store.record_financial_finding('one','mixed',finding(3,'x','y',2))
    second,_=store.record_financial_finding('one','mixed',finding(4,'x','z',3))
    assert second.case_id!=first.case_id
    assert len(store.list_financial_investigations())==2
    store.record_financial_finding('two','mule',finding(1,'a','b'))
    isolated,_=store.record_financial_finding('two','mule',finding(2,'b','c',1))
    assert isolated.case_id!=first.case_id
    assert len(store.list_financial_investigations(session_id='one'))==2
    # Bridge evidence merges cases without deleting their stable historical IDs.
    merged,_=store.record_financial_finding('one','mixed',finding(5,'c','x',4))
    assert len(store.list_financial_investigations(session_id='one'))==1
    assert store.get_financial_investigation(second.case_id).case_id==merged.case_id
    # New store instance represents an application restart on the same database.
    reopened=ArgusStore(store.path)
    assert reopened.get_financial_investigation(first.case_id).transaction_ids==merged.transaction_ids
    assert len(reopened.list_financial_investigations())==2


def test_admission_window_and_concurrent_replay(tmp_path):
    store=ArgusStore(tmp_path/'concurrent.db')
    store.record_financial_finding('s',None,finding(1,'a','b'))
    assert store.record_financial_finding('s',None,finding(2,'b','c',901))==(None,False)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: store.record_financial_finding('s',None,finding(3,'c','d',902)), range(8)))
    cases=store.list_financial_investigations()
    assert len(cases)==1 and set(cases[0].transaction_ids)=={'PAY-2','PAY-3'}


def scenario_payments(kind):
    if kind=='normal':
        return [payment(i,source=f'customer-{i}',target=f'merchant-{i%4}',seconds=i*180) for i in range(20)]
    baseline=[payment(i,source='owner',target=f'known-{i}',seconds=i) for i in range(12)]
    if kind=='mule':
        return baseline+[payment(12+i,source=f'mule-{i%4}',target=f'mule-{i%4+1}',amount=180000-(i%4)*4500,seconds=12+i) for i in range(8)]
    if kind=='takeover':
        return baseline+[payment(12+i,source='owner',target=f'new-{i}',amount=275000+i*10000,seconds=12+i,device='new-device') for i in range(8)]
    if kind=='fanout':
        return baseline+[payment(12+i,source='scam-source',target=f'victim-{i}',amount=48000,seconds=12+i) for i in range(8)]
    if kind=='mixed':
        return [payment(i,source=f'mule-{i%4}',target=f'mule-{i%4+1}',amount=180000-(i%4)*4500,seconds=i) for i in range(8)]+[payment(20+i,source='scam-source',target=f'victim-{i}',amount=48000,seconds=20+i) for i in range(8)]
    raise AssertionError(kind)


@pytest.mark.parametrize('kind',['normal','mule','takeover','fanout','mixed'])
def test_actual_detector_to_case_api_flow(kind,mock_gateway,isolated_manager):
    with TestClient(app) as client:
        for payload in scenario_payments(kind):
            assert client.post(f'/api/transactions?session_id=run-{kind}&scenario_id={kind}',json=payload).status_code==201
        cases=client.get(f'/api/financial-investigations?session_id=run-{kind}').json()
        if kind=='normal':
            assert cases==[]
            return
        assert cases, f'{kind} should have at least two related detector-qualified completed payments'
        if kind=='mixed':
            assert len(cases)>=2
        case=cases[0]
        assert case['source']=='Synthetic Stream' and case['scenario_id']==kind
        assert len(case['transaction_ids'])>=2 and case['evidence']
        assert 'infrastructure_signal_id' not in case
        assert client.get(f"/api/financial-investigations/{case['case_id']}").json()==case
        context=client.get(f"/api/financial-investigations/{case['case_id']}/context").json()
        assert context['transactions'] and context['events']
        txid=case['transaction_ids'][0]
        assert any(tx['transaction_id']==txid for tx in client.get(f'/api/transactions/{txid}/context').json()['transactions'])
        events=client.get(f'/api/transaction-events?session_id=run-{kind}').json()
        assert any(e['event_type']=='investigation.updated' for e in events)
        # Duplicate ingestion and reconnect-style replay are read/idempotent operations.
        for payload in scenario_payments(kind):
            assert client.post(f'/api/transactions?session_id=run-{kind}&scenario_id={kind}',json=payload).status_code==200
        assert client.get(f'/api/financial-investigations?session_id=run-{kind}').json()==cases
        assert client.get(f'/api/transaction-events?session_id=run-{kind}').json()==events
        assert client.get('/api/financial-investigations/not-found').status_code==404
        assert client.get('/api/transactions/missing/context').status_code==404


def test_old_transaction_context_survives_history_limit_and_filters_other_sessions():
    store=app.dependency_overrides[get_argus_store]()
    older=Transaction.model_validate(payment('old',seconds=0))
    store.ingest_transaction(older,'old-session')
    store.save_stream_event('old-session',dict(event_id='old-score',event_type='transaction.scored',timestamp=BASE.isoformat(),data={'transaction_id':older.transaction_id,'risk_score':.9}))
    for i in range(250):
        store.ingest_transaction(Transaction.model_validate(payment(i,seconds=10000+i)),'other-session')
    with TestClient(app) as client:
        assert older.transaction_id not in [tx['transaction_id'] for tx in client.get('/api/transactions?limit=200').json()]
        context=client.get(f'/api/transactions/{older.transaction_id}/context').json()
        assert context['session_id']=='old-session'
        assert [tx['transaction_id'] for tx in context['transactions']]==[older.transaction_id]
        assert context['events'][0]['event_id']=='old-score'
        assert client.get('/api/incidents/missing/context').status_code==404


def test_out_of_order_findings_join_once_without_crossing_the_admission_window(tmp_path):
    store=ArgusStore(tmp_path/'late.db')
    store.record_financial_finding('s','mule',finding(2,'b','c',5))
    case,_=store.record_financial_finding('s','mule',finding(1,'a','b',0))
    assert case.transaction_ids==['PAY-1','PAY-2']
    assert case.last_activity_at==BASE+timedelta(seconds=5)
    store.record_financial_finding('other','mule',finding(1,'a','b',0))
    assert store.record_financial_finding('other','mule',finding(2,'b','c',1801))==(None,False)
