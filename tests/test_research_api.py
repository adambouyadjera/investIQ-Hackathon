import sys
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.routers import research
from app.routers.auth import get_current_user

class ResearchAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.override=patch.object(research,'ACCOUNTS',Path(self.tmp.name));self.override.start()
        self.app=FastAPI();self.app.include_router(research.router)
        self.user=SimpleNamespace(id=uuid4())
        self.app.dependency_overrides[get_current_user]=lambda:self.user
        self.client=TestClient(self.app)
    def tearDown(self):
        self.client.close();self.override.stop();self.tmp.cleanup()
    def test_auth_required(self):
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get('/research').status_code,401)
    def test_accounts_isolated(self):
        first=self.user
        self.assertEqual(self.client.post('/research/paper/control',json={'action':'start'}).status_code,200)
        self.user=SimpleNamespace(id=uuid4())
        self.assertFalse(self.client.get('/research').json()['paper']['enabled'])
        self.user=first
        self.assertTrue(self.client.get('/research').json()['paper']['enabled'])
    def test_invalid_control_rejected(self):
        self.assertEqual(self.client.post('/research/paper/control',json={'action':'live'}).status_code,422)
    def test_network_failure_persists_safe_status(self):
        with patch.object(research,'snapshot',side_effect=RuntimeError('private internal detail')):
            r=self.client.post('/research/paper/check')
        self.assertEqual(r.status_code,200)
        state=r.json();self.assertEqual(state['status'],'data_unavailable')
        self.assertNotIn('private',state['error']);self.assertIsNone(state['position'])
        self.assertEqual(self.client.get('/research').json()['paper']['status'],'data_unavailable')
    def test_report_and_journal(self):
        r=self.client.get('/research').json()['research']
        self.assertEqual(r['configurations_tested'],70)
        self.assertEqual(r['passed_candidates'],0)
        self.assertIn('research',self.client.get('/research/journal').text.lower())
