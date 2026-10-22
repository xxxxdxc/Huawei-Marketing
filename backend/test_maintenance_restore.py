"""Restore is authenticated, bounded, one-use, and never overwrites newer tasks."""
import copy,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.test_workflow import prepared
from backend.main import app
from backend import maintenance_restore as mr,storage as db

class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app);self.client.__enter__();self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.patch=patch.object(mr,'DATA',self.root);self.patch.start();self.addCleanup(self.patch.stop)
    def tearDown(self):self.client.__exit__(None,None,None)
    def post(self,data,key='x'*32):return self.client.post('/api/maintenance/restore',json=data,headers={'X-Maintenance-Key':key})
    def test_disabled_without_key_and_wrong_key_rejected(self):
        with patch.dict(os.environ,{'HUAWEI_MAINTENANCE_KEY':''}):self.assertEqual(self.post({'tasks':[]}).status_code,404)
        with patch.dict(os.environ,{'HUAWEI_MAINTENANCE_KEY':'x'*32}):self.assertEqual(self.post({'tasks':[]},'bad').status_code,401)
    def test_restore_preserves_existing_and_closes_after_one_use(self):
        current=prepared();new=copy.deepcopy(current);new['id']='d'*32
        # Test IDs are unique even when imported with other modules.
        new['id']=__import__('uuid').uuid4().hex;before=copy.deepcopy(db.get(current['id']))
        with patch.dict(os.environ,{'HUAWEI_MAINTENANCE_KEY':'x'*32}):
            r=self.post({'tasks':[current,new]});self.assertEqual(r.status_code,200);self.assertIn(current['id'],r.json()['skipped'])
            self.assertEqual(db.get(current['id']),before);self.assertIsNone(db.get(new['id'])['review'])
            self.assertEqual(self.post({'tasks':[new]}).status_code,409)
    def test_path_traversal_and_bad_assets_do_not_import(self):
        t=prepared();t['id']='../escape'
        with patch.dict(os.environ,{'HUAWEI_MAINTENANCE_KEY':'x'*32}):
            self.assertEqual(self.post({'tasks':[t]}).status_code,400)
            t['id']=__import__('uuid').uuid4().hex
            self.assertEqual(self.post({'tasks':[t],'assets':[{'id':'../bad','body':'YQ==','sha256':'x'}]}).status_code,400)
        with self.assertRaises(KeyError):db.get(t['id'])
