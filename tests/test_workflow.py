from fastapi.testclient import TestClient
from app import SAMPLE, create_app, extract


def test_parser_preserves_evidence_and_unknowns():
    result = extract(SAMPLE)
    assert len(result) == 4
    assert result[0]['owner'] == 'Asha'
    assert result[2]['due_date'] == ''
    assert all(SAMPLE.splitlines()[task['source_line']-1] == task['source_quote'] for task in result)
    assert extract('We should talk about our strategy later.') == []


def test_approval_publishing_replay_and_isolation(tmp_path):
    app = create_app(tmp_path/'plans.db')
    with TestClient(app) as a, TestClient(app) as b:
        p = a.post('/api/plans',json={'transcript':SAMPLE}).json()
        assert b.get('/api/plans/'+p['id']).status_code == 404
        assert a.post('/api/plans/'+p['id']+'/publish',json={'idempotency_key':'test-key-123'}).status_code == 409
        review = {'version':1,'decision':'approve','tasks':p['tasks']}
        approved = a.post('/api/plans/'+p['id']+'/review',json=review)
        assert approved.status_code == 200 and approved.json()['state'] == 'approved'
        assert a.post('/api/plans/'+p['id']+'/review',json=review).status_code == 409
        url = '/api/plans/'+p['id']+'/publish'
        first = a.post(url,json={'idempotency_key':'test-key-123'}).json()
        replay = a.post(url,json={'idempotency_key':'other-key-456'}).json()
        assert len(first['issues']) == 4 and replay['issues'] == first['issues']
        assert len([e for e in replay['events'] if e['action']=='published']) == 1
        assert b.post(url,json={'idempotency_key':'test-key-123'}).status_code == 404


def test_rejection_and_input_failures(tmp_path):
    with TestClient(create_app(tmp_path/'plans.db')) as c:
        assert c.get('/').status_code == 200
        assert c.get('/static/app.js').status_code == 200
        assert c.post('/api/plans',json={'transcript':'No clear commitment in this discussion.'}).status_code == 422
        assert c.post('/api/plans',content='x'*50001).status_code == 413
        assert c.post('/api/plans',json={'transcript':SAMPLE},headers={'Origin':'https://untrusted.example'}).status_code == 403
        p = c.post('/api/plans',json={'transcript':SAMPLE}).json()
        assert c.post('/api/plans/'+p['id']+'/review',json={'version':1,'decision':'reject','tasks':p['tasks']}).json()['state']=='rejected'
        assert c.post('/api/plans/'+p['id']+'/publish',json={'idempotency_key':'test-key-123'}).status_code==409


def test_metadata_boundaries_calendar_dates_and_priority():
    tasks = extract("Action: Add request validation | Owner: Asha | Due: 2026-11-06 | Priority: high\nTODO: Write SQL tests. Owner: Kabir Due: 2026-02-30 Priority: low")
    assert tasks[0]['title'] == 'Add request validation'
    assert tasks[0]['owner'] == 'Asha'
    assert tasks[0]['due_date'] == '2026-11-06'
    assert tasks[0]['priority'] == 'high'
    assert tasks[1]['owner'] == 'Kabir'
    assert tasks[1]['due_date'] == ''
    assert tasks[1]['priority'] == 'low'
    assert tasks[0]['acceptance'] == ''


def test_altered_evidence_cannot_override_original_source(tmp_path):
    with TestClient(create_app(tmp_path/'plans.db')) as client:
        plan = client.post('/api/plans', json={'transcript':SAMPLE}).json()
        tasks = plan['tasks']
        original = tasks[0]['source_quote']
        tasks[0].update(title='Edited task with human context', source_quote='Fabricated source', source_line=999)
        response = client.post(f"/api/plans/{plan['id']}/review", json={'version':1,'decision':'approve','tasks':tasks})
        assert response.status_code == 200
        assert response.json()['tasks'][0]['source_quote'] == original
        assert response.json()['tasks'][0]['title'] == 'Edited task with human context'


def test_invalid_review_is_atomic_and_foreign_tasks_are_refused(tmp_path):
    with TestClient(create_app(tmp_path/'plans.db')) as client:
        plan = client.post('/api/plans', json={'transcript':SAMPLE}).json()
        tasks = plan['tasks']
        tasks[0]['due_date'] = '2026-02-30'
        url = f"/api/plans/{plan['id']}/review"
        response = client.post(url, json={'version':1,'decision':'approve','tasks':tasks})
        assert response.status_code == 422
        assert client.get(f"/api/plans/{plan['id']}").json()['state'] == 'draft'
        tasks[0]['due_date'] = ''
        tasks[0]['id'] = 'foreign-task'
        assert client.post(url,json={'version':1,'decision':'approve','tasks':tasks}).status_code == 422
        tasks[0]['id'] = tasks[1]['id']
        assert client.post(url,json={'version':1,'decision':'approve','tasks':tasks}).status_code == 422


def test_concurrent_publish_creates_one_issue_set_and_event(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    with TestClient(create_app(tmp_path/'plans.db')) as client:
        plan = client.post('/api/plans',json={'transcript':SAMPLE}).json()
        client.post(f"/api/plans/{plan['id']}/review",json={'version':1,'decision':'approve','tasks':plan['tasks']}).raise_for_status()
        def publish(index):
            response = client.post(f"/api/plans/{plan['id']}/publish",json={'idempotency_key':f'concurrent-key-{index}'})
            response.raise_for_status()
            return response.json()
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(publish, range(4)))
        assert all(len(result['issues']) == 4 for result in results)
        assert all(result['issues'] == results[0]['issues'] for result in results)
        assert sum(event['action']=='published' for event in results[-1]['events']) == 1


def test_records_survive_restart_with_the_same_session(tmp_path):
    path = tmp_path/'plans.db'
    with TestClient(create_app(path)) as first:
        plan = first.post('/api/plans',json={'transcript':SAMPLE}).json()
        cookie = first.cookies.get('sprint_session')
    with TestClient(create_app(path)) as second:
        second.cookies.set('sprint_session',cookie)
        restored = second.get('/api/plans/'+plan['id'])
        assert restored.status_code == 200
        assert restored.json()['tasks'] == plan['tasks']


def test_other_session_cannot_review_or_export_plan(tmp_path):
    with TestClient(create_app(tmp_path/'plans.db')) as client:
        plan = client.post('/api/plans',json={'transcript':SAMPLE}).json()
        client.cookies.clear()
        assert client.get('/api/plans/'+plan['id']).status_code == 404
        assert client.post(f"/api/plans/{plan['id']}/review",json={'version':1,'decision':'approve','tasks':plan['tasks']}).status_code == 404


def test_twelve_task_cap_preserves_original_line_numbers():
    text = '\n'.join(f'TODO: Complete task number {number}' for number in range(20))
    tasks = extract(text)
    assert len(tasks) == 12
    assert tasks[-1]['source_line'] == 12
