import json

import httpx
import pytest
from fastapi.testclient import TestClient

import app as application
from integrations import IntegrationError, create_jira_issue, extract_proposals


def llm(monkeypatch, tasks):
    monkeypatch.setenv('SPRINT_LLM_API_KEY','test-key')
    monkeypatch.setenv('SPRINT_LLM_MODEL','test-model')
    return httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'tasks':tasks})}}]}))


def test_unstructured_proposal_evidence_and_unknown_metadata(monkeypatch):
    line='We need API input validation before release.'
    task={'title':'Add API input validation','owner':'Invented','due_date':'2026-11-01','priority':'high','acceptance':'Validation tests pass','source_line':1,'source_quote':line}
    result=extract_proposals(line,llm(monkeypatch,[task]))
    assert result[0]['owner']=='' and result[0]['due_date']=='' and result[0]['priority']=='unknown'
    assert result[0]['source_quote']==line


@pytest.mark.parametrize('change',[{'source_quote':'fiction'},{'source_line':2},{'priority':'urgent'}])
def test_invalid_proposals_fail(monkeypatch,change):
    line='Add API validation.'
    task={'title':'Add API validation','source_line':1,'source_quote':line,**change}
    with pytest.raises(IntegrationError):extract_proposals(line,llm(monkeypatch,[task]))


def jira_env(monkeypatch):
    for key,value in {'URL':'https://example.atlassian.net','EMAIL':'test@example.com','API_TOKEN':'test-token','PROJECT':'TEST','PUBLISH_TOKEN':'operator-only-test-token'}.items():
        monkeypatch.setenv('SPRINT_JIRA_'+key,value)


def approve(client):
    plan=client.post('/api/plans',json={'transcript':'Action: Add API validation. Owner: Asha'}).json()
    return client.post('/api/plans/'+plan['id']+'/review',json={'version':plan['version'],'decision':'approve','tasks':plan['tasks']}).json()


def test_jira_adapter_builds_real_request_without_network(monkeypatch):
    jira_env(monkeypatch)
    def handle(request):
        body=json.loads(request.content)
        assert request.url.path=='/rest/api/3/issue'
        assert body['fields']['labels']==['marker']
        assert body['fields']['project']['key']=='TEST'
        return httpx.Response(201,json={'key':'TEST-7'})
    task={'title':'Add validation','owner':'Asha','acceptance':'tests pass','source_line':1,'source_quote':'Action: Add validation','due_date':''}
    result=create_jira_issue(task,'marker',httpx.MockTransport(handle))
    assert result['url']=='https://example.atlassian.net/browse/TEST-7'


def test_jira_requires_approval_token_and_reuses_created(monkeypatch,tmp_path):
    jira_env(monkeypatch); calls=[]
    monkeypatch.setattr(application,'create_jira_issue',lambda task,marker:(calls.append(marker) or {'key':'TEST-1','url':'https://example.atlassian.net/browse/TEST-1'}))
    with TestClient(application.create_app(tmp_path/'plans.db')) as client:
        draft=client.post('/api/plans',json={'transcript':'Action: Add validation'}).json()
        path='/api/plans/'+draft['id']+'/publish/jira'
        body={'expected_version':1,'confirm_external_write':True};headers={'X-Publish-Token':'operator-only-test-token'}
        assert client.post(path,json=body,headers=headers).status_code==409
        plan=approve(client);path='/api/plans/'+plan['id']+'/publish/jira';body['expected_version']=plan['version']
        assert client.post(path,json=body).status_code==403
        assert client.post(path,json=body,headers=headers).status_code==200
        assert client.post(path,json=body,headers=headers).status_code==200
        assert len(calls)==1


def test_unknown_jira_outcome_blocks_retry_even_after_restart(monkeypatch,tmp_path):
    jira_env(monkeypatch);calls=[];db=tmp_path/'plans.db'
    def fail(task,marker):calls.append(marker);raise IntegrationError('Jira outcome uncertain')
    monkeypatch.setattr(application,'create_jira_issue',fail)
    with TestClient(application.create_app(db)) as client:
        plan=approve(client);cookies=dict(client.cookies);path='/api/plans/'+plan['id']+'/publish/jira';body={'expected_version':plan['version'],'confirm_external_write':True};headers={'X-Publish-Token':'operator-only-test-token'}
        assert client.post(path,json=body,headers=headers).status_code==502
    with TestClient(application.create_app(db)) as client:
        client.cookies.update(cookies)
        assert client.post(path,json=body,headers=headers).status_code==409
        assert len(calls)==1


def test_llm_unconfigured_draft_fails(monkeypatch,tmp_path):
    monkeypatch.delenv('SPRINT_LLM_API_KEY',raising=False)
    with TestClient(application.create_app(tmp_path/'plans.db')) as client:
        assert client.post('/api/plans',json={'transcript':'Some unstructured notes on validation','engine':'semantic'}).status_code==503


def test_reconciliation_verifies_marker_before_unblocking(monkeypatch,tmp_path):
    jira_env(monkeypatch)
    def fail(task,marker):raise IntegrationError('timeout')
    monkeypatch.setattr(application,'create_jira_issue',fail)
    with TestClient(application.create_app(tmp_path/'plans.db')) as client:
        plan=approve(client);base='/api/plans/'+plan['id'];headers={'X-Publish-Token':'operator-only-test-token'}
        assert client.post(base+'/publish/jira',json={'expected_version':plan['version'],'confirm_external_write':True},headers=headers).status_code==502
        task_id=plan['tasks'][0]['id']
        def reject(key,marker):raise IntegrationError('marker mismatch')
        monkeypatch.setattr(application,'verify_jira_issue',reject)
        body={'task_id':task_id,'issue_key':'TEST-9'}
        assert client.post(base+'/reconcile/jira',json=body,headers=headers).status_code==502
        monkeypatch.setattr(application,'verify_jira_issue',lambda key,marker:{'key':key,'url':'https://example.atlassian.net/browse/'+key})
        assert client.post(base+'/reconcile/jira',json=body,headers=headers).json()['jira_exports'][0]['state']=='created'


def test_existing_issue_marker_is_checked(monkeypatch):
    from integrations import verify_jira_issue
    jira_env(monkeypatch)
    transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'fields':{'labels':['other-marker']}}))
    with pytest.raises(IntegrationError):verify_jira_issue('TEST-1','expected-marker',transport)


def test_ai_operator_token_blocks_provider_before_call(monkeypatch,tmp_path):
    monkeypatch.setenv('SPRINT_LLM_API_KEY','test-key')
    monkeypatch.setenv('SPRINT_LLM_MODEL','test-model')
    monkeypatch.setenv('SPRINT_LLM_ACCESS_TOKEN','operator-secret')
    calls=[]
    monkeypatch.setattr(application,'extract_proposals',lambda *args:calls.append(args))
    with TestClient(application.create_app(tmp_path/'plans.db')) as client:
        payload={'transcript':'Some unstructured notes on validation','engine':'semantic'}
        assert client.post('/api/plans',json=payload).status_code==403
        assert client.post('/api/plans',json=payload,headers={'X-AI-Token':'wrong'}).status_code==403
        assert not calls


def test_authorized_ai_proposals_are_drafts_not_issues(monkeypatch,tmp_path):
    line='We need input validation.'
    result=extract_proposals(line,llm(monkeypatch,[{'title':'Add input validation','source_line':1,'source_quote':line}]))
    monkeypatch.setenv('SPRINT_LLM_ACCESS_TOKEN','operator-secret')
    monkeypatch.setattr(application,'extract_proposals',lambda *args:result)
    with TestClient(application.create_app(tmp_path/'plans.db')) as client:
        response=client.post('/api/plans',json={'transcript':line,'engine':'semantic'},headers={'X-AI-Token':'operator-secret'})
        assert response.status_code==201
        assert response.json()['state']=='draft' and response.json()['issues']==[] and response.json()['jira_exports']==[]
