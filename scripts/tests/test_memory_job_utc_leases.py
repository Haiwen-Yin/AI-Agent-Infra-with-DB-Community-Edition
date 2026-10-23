"""Deterministic Memory job fencing under non-UTC database session clocks."""
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import re
import sqlite3
import threading

import pytest

from lib import memory_lifecycle as memory


@pytest.fixture(params=[-4, 8], ids=['utc-minus-four', 'utc-plus-eight'])
def jobs(request, monkeypatch):
    clock = [datetime(2030, 6, 1, 12, 1, 2, 345678, tzinfo=timezone.utc)]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)
    monkeypatch.setattr(memory, 'datetime', Clock)
    db = sqlite3.connect(':memory:', check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.create_function('current_timestamp', 0,
        lambda: (clock[0] + timedelta(hours=request.param)).replace(tzinfo=None).isoformat(sep=' '))
    db.executescript('''
        CREATE TABLE CX_MEMORY_JOBS(JOB_ID TEXT PRIMARY KEY, STATUS TEXT, LEASE_OWNER TEXT,
            LEASE_EXPIRES_AT TIMESTAMP, FENCING_TOKEN INTEGER DEFAULT 0, CHECKPOINT_JSON TEXT,
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UPDATED_AT TIMESTAMP);
        CREATE TABLE CX_MEMORY_JOB_ITEMS(ITEM_ID TEXT PRIMARY KEY, JOB_ID TEXT,
            STATUS TEXT, LEASE_OWNER TEXT, LEASE_EXPIRES_AT TIMESTAMP,
            FENCING_TOKEN INTEGER DEFAULT 0, ATTEMPT_COUNT INTEGER DEFAULT 0, RESULT_JSON TEXT,
            SUBJECT_VERSION_ID TEXT DEFAULT 'version', INPUT_DIGEST TEXT DEFAULT 'input',
            CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UPDATED_AT TIMESTAMP);
        CREATE TABLE CX_MEMORY_WORKER_RESULTS(RESULT_ID TEXT PRIMARY KEY,JOB_ITEM_ID TEXT,WORKER_ID TEXT,
            FENCING_TOKEN INTEGER,INPUT_DIGEST TEXT,OUTPUT_DIGEST TEXT,SCHEMA_VERSION TEXT,RESULT_JSON TEXT,VALIDATION_STATE TEXT);
        CREATE TABLE CX_MEMORY_CANDIDATES(CANDIDATE_ID TEXT PRIMARY KEY,CANDIDATE_TYPE TEXT,SOURCE_VERSION_ID TEXT,
            PROPOSED_JSON TEXT,CONFIDENCE REAL,STATUS TEXT,POLICY_RESULT TEXT,CREATED_BY TEXT,REASON TEXT,IDEMPOTENCY_KEY TEXT);
        INSERT INTO CX_MEMORY_JOBS(JOB_ID,STATUS) VALUES('job','QUEUED');
        INSERT INTO CX_MEMORY_JOB_ITEMS(ITEM_ID,JOB_ID,STATUS) VALUES('item','job','QUEUED');
    ''')
    def query(sql, params):
        sql = re.sub(r' FETCH FIRST :(\w+) ROWS ONLY', r' LIMIT :\1', sql)
        sql = sql.replace(' FOR UPDATE', '')
        values = db.execute(sql, params).fetchall()
        return [{key.lower(): row[key] for key in row.keys()} for row in values]
    monkeypatch.setattr(memory, 'execute_query_one', lambda sql, params: next(iter(query(sql, params)), None))
    monkeypatch.setattr(memory, 'execute', lambda sql, params: db.execute(sql, params).rowcount)
    class Tx:
        def query_one(self, sql, params):
            return next(iter(query(sql, params)), None)
        def execute(self, sql, params):
            return db.execute(sql, params).rowcount
    transaction_lock = threading.Lock()
    def transaction(callback):
        with transaction_lock:
            try:
                value = callback(Tx())
                db.commit()
                return value
            except Exception:
                db.rollback()
                raise
    monkeypatch.setattr(memory, 'execute_transaction_callback', transaction)
    yield db, clock
    db.close()


def test_job_claim_renew_and_completion_follow_utc_not_session_clock(jobs):
    db, clock = jobs
    first = memory.claim_job('worker', lease_seconds=30)
    assert first['fencing_token'] == 1
    assert memory.claim_job('other-worker') is None
    assert memory.renew_job_lease('job', worker_id='worker', fencing_token=1, lease_seconds=30)
    assert memory.complete_job('job', worker_id='worker', fencing_token=1, result={'done': True})
    assert db.execute('SELECT LEASE_EXPIRES_AT FROM CX_MEMORY_JOBS').fetchone()[0] == clock[0].replace(tzinfo=None).isoformat(sep=' ')


def test_expired_job_cannot_renew_or_complete_and_reclaim_fences_old_worker(jobs):
    _, clock = jobs
    memory.claim_job('old-worker', lease_seconds=30)
    clock[0] += timedelta(seconds=31)
    assert not memory.renew_job_lease('job', worker_id='old-worker', fencing_token=1)
    assert not memory.complete_job('job', worker_id='old-worker', fencing_token=1, result={'late': True})
    fresh = memory.claim_job('new-worker', lease_seconds=30)
    assert fresh['fencing_token'] == 2 and fresh['lease_owner'] == 'new-worker'
    assert not memory.complete_job('job', worker_id='old-worker', fencing_token=1, result={'late': True})
    assert memory.complete_job('job', worker_id='new-worker', fencing_token=2, result={'done': True})


def test_item_reclaim_and_completion_are_fenced_by_exact_utc_deadline(jobs):
    _, clock = jobs
    memory.claim_job('worker', lease_seconds=120)
    item = memory.claim_job_item('job', worker_id='worker', job_fencing_token=1, lease_seconds=30)
    assert item['fencing_token'] == 1
    assert memory.claim_job_item('job', worker_id='worker', job_fencing_token=1) is None
    clock[0] += timedelta(seconds=31)
    assert not memory.complete_job_item('item', worker_id='worker', fencing_token=1, result={'late': True})
    fresh = memory.claim_job_item('job', worker_id='worker', job_fencing_token=1)
    assert fresh['fencing_token'] == 2 and fresh['attempt_count'] == 2
    assert not memory.complete_job_item('item', worker_id='worker', fencing_token=1, result={'late': True})
    assert memory.complete_job_item('item', worker_id='worker', fencing_token=2, result={'done': True})


def test_live_item_cannot_complete_after_its_parent_lease_expires(jobs):
    _, clock = jobs
    memory.claim_job('worker', lease_seconds=30)
    memory.claim_job_item('job', worker_id='worker', job_fencing_token=1, lease_seconds=120)
    clock[0] += timedelta(seconds=31)
    assert not memory.complete_job_item('item', worker_id='worker', fencing_token=1, result={'late': True})


def test_expired_parent_or_wrong_parent_fence_cannot_claim_item(jobs):
    _, clock = jobs
    memory.claim_job('worker', lease_seconds=30)
    assert memory.claim_job_item('job', worker_id='worker', job_fencing_token=2) is None
    clock[0] += timedelta(seconds=31)
    assert memory.claim_job_item('job', worker_id='worker', job_fencing_token=1) is None


def submit_result():
    return memory.submit_external_worker_result('item', worker_id='worker', fencing_token=1,
        input_digest='input', output={'summary': 'A finding requiring independent review.'})


def test_external_result_candidate_and_completion_commit_once_together(jobs, monkeypatch):
    db, _ = jobs
    memory.claim_job('worker')
    memory.claim_job_item('job', worker_id='worker', job_fencing_token=1)
    db.commit()
    monkeypatch.setattr(memory, 'execute', lambda *_: pytest.fail('Acceptance writes must use the current transaction'))
    value = submit_result()
    assert value['candidate']['status'] == 'PENDING'
    assert db.execute('SELECT STATUS FROM CX_MEMORY_CANDIDATES').fetchone()[0] == 'PENDING'
    assert db.execute('SELECT STATUS FROM CX_MEMORY_JOB_ITEMS').fetchone()[0] == 'COMPLETED'
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_WORKER_RESULTS').fetchone()[0] == 1
    with pytest.raises(memory.MemoryLifecycleError, match='lease is unavailable'):
        submit_result()
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_CANDIDATES').fetchone()[0] == 1


@pytest.mark.parametrize('invalid', ['expired-item', 'expired-parent', 'wrong-worker', 'wrong-fence', 'changed-input'])
def test_external_result_rejection_writes_no_result_or_candidate(jobs, invalid):
    db, clock = jobs
    memory.claim_job('worker', lease_seconds=30 if invalid == 'expired-parent' else 120)
    memory.claim_job_item('job', worker_id='worker', job_fencing_token=1,
                          lease_seconds=30 if invalid == 'expired-item' else 120)
    if invalid.startswith('expired-'):
        clock[0] += timedelta(seconds=31)
    elif invalid == 'wrong-worker':
        db.execute("UPDATE CX_MEMORY_JOBS SET LEASE_OWNER='other'")
    elif invalid == 'wrong-fence':
        db.execute('UPDATE CX_MEMORY_JOB_ITEMS SET FENCING_TOKEN=2')
    else:
        db.execute("UPDATE CX_MEMORY_JOB_ITEMS SET INPUT_DIGEST='changed'")
    db.commit()
    with pytest.raises(memory.MemoryLifecycleError):
        submit_result()
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_WORKER_RESULTS').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_CANDIDATES').fetchone()[0] == 0
    assert db.execute('SELECT STATUS FROM CX_MEMORY_JOB_ITEMS').fetchone()[0] == 'RUNNING'


def test_lease_expiry_during_candidate_acceptance_rolls_back_all_writes(jobs, monkeypatch):
    db, clock = jobs
    memory.claim_job('worker', lease_seconds=30)
    memory.claim_job_item('job', worker_id='worker', job_fencing_token=1, lease_seconds=30)
    db.commit()
    original = memory.propose_llm_candidate
    def crossing_deadline(*args, **kwargs):
        value = original(*args, **kwargs)
        clock[0] += timedelta(seconds=31)
        return value
    monkeypatch.setattr(memory, 'propose_llm_candidate', crossing_deadline)
    with pytest.raises(memory.MemoryLifecycleError, match='completion was superseded'):
        submit_result()
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_WORKER_RESULTS').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_CANDIDATES').fetchone()[0] == 0
    assert db.execute('SELECT STATUS FROM CX_MEMORY_JOB_ITEMS').fetchone()[0] == 'RUNNING'


def test_concurrent_result_submissions_accept_only_one_exact_fenced_item(jobs):
    db, _ = jobs
    memory.claim_job('worker')
    memory.claim_job_item('job', worker_id='worker', job_fencing_token=1)
    db.commit()
    barrier = threading.Barrier(2)
    def submit(_):
        barrier.wait(timeout=5)
        try:
            return submit_result()['candidate']['status']
        except memory.MemoryLifecycleError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(submit, range(2)))
    assert sorted(outcomes) == ['FENCING_REJECTED', 'PENDING']
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_WORKER_RESULTS').fetchone()[0] == 1
    assert db.execute('SELECT COUNT(*) FROM CX_MEMORY_CANDIDATES').fetchone()[0] == 1
