"""Proxy Origin regression tests use invalid bodies and never call models."""
import os
import unittest
from unittest.mock import AsyncMock, patch
from backend.test_workflow import TEST_DATA
from fastapi.testclient import TestClient
from backend.main import app
from backend import workflow as w

PUBLIC='https://xxxxcxc-huawei-marketing.ms.show'

class ProxyOriginTests(unittest.TestCase):
    def request(self,origin,configured='',headers=None,method='POST'):
        with patch.dict(os.environ,{'HUAWEI_ALLOWED_ORIGINS':configured}):
            with TestClient(app) as client:
                h=dict(headers or {})
                if origin is not None:h['Origin']=origin
                return client.request(method,'/api/tasks',json={},headers=h)

    def test_explicit_public_origin_survives_proxy_host_rewrite(self):
        r=self.request(PUBLIC,PUBLIC)
        self.assertEqual(r.status_code,422,r.text)

    def test_local_same_origin_remains_valid(self):
        self.assertEqual(self.request('http://testserver').status_code,422)

    def test_unconfigured_public_origin_is_rejected(self):
        self.assertEqual(self.request(PUBLIC).status_code,403)

    def test_unrelated_origin_and_forwarded_header_spoof_are_rejected(self):
        r=self.request('https://unrelated.example',PUBLIC,{'X-Forwarded-Host':'xxxxcxc-huawei-marketing.ms.show','X-Forwarded-Proto':'https'})
        self.assertEqual(r.status_code,403)

    def test_exact_origin_match_not_suffix_or_path_match(self):
        for origin in [PUBLIC+'.evil.example',PUBLIC+':444',PUBLIC+':0',PUBLIC+'/anything',PUBLIC+'?x=1',PUBLIC+'#fragment','null','https://someone@xxxxcxc-huawei-marketing.ms.show']:
            with self.subTest(origin=origin):self.assertEqual(self.request(origin,PUBLIC).status_code,403)

    def test_default_port_normalization(self):
        self.assertEqual(self.request(PUBLIC+':443',PUBLIC).status_code,422)
        self.assertEqual(self.request('http://testserver:80').status_code,422)

    def test_multiple_explicit_origins(self):
        self.assertEqual(self.request(PUBLIC,'https://other.example, '+PUBLIC+'/').status_code,422)

    def test_wildcard_origin_configuration_does_not_allow_arbitrary_websites(self):
        self.assertEqual(self.request('https://unrelated.example','*').status_code,403)

    def test_non_browser_requests_without_origin_remain_valid(self):
        self.assertEqual(self.request(None,PUBLIC).status_code,422)

    def test_same_host_different_scheme_is_not_same_origin(self):
        self.assertEqual(self.request('https://testserver').status_code,403)

    def test_write_methods_all_enforce_origin(self):
        for method in ['POST','PUT','PATCH','DELETE']:
            with self.subTest(method=method):self.assertEqual(self.request('https://unrelated.example',PUBLIC,method=method).status_code,403)

    def test_read_request_does_not_authorize_a_write(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/health',headers={'Origin':'https://unrelated.example'}).status_code,200)

    def test_rejection_has_actionable_json_and_response_headers(self):
        r=self.request('https://unrelated.example',PUBLIC)
        self.assertEqual(r.status_code,403)
        self.assertIsInstance(r.json()['detail'],str)
        self.assertEqual(r.headers.get('Cache-Control'),'no-store')
        self.assertEqual(r.headers.get('X-Content-Type-Options'),'nosniff')

    def test_proxy_origin_allows_create_and_start_without_real_model(self):
        with patch.dict(os.environ,{'HUAWEI_ALLOWED_ORIGINS':PUBLIC}):
            with TestClient(app) as client, patch.object(w,'job',AsyncMock()) as job:
                response=client.post('/api/tasks',headers={'Origin':PUBLIC},json={'raw':'隔离模拟营销需求，不是真实业务任务','platform':'moments','knowledge_source':'ima'})
                self.assertEqual(response.status_code,201,response.text)
                task=response.json()
                response=client.post(f"/api/tasks/{task['id']}/analyze",headers={'Origin':PUBLIC},json={'version':task['version']})
                self.assertEqual(response.status_code,202,response.text)
                job.assert_awaited_once_with(task['id'],'analyze')
