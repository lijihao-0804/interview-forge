"""Real session cookies and zip fixtures exercise the private content boundary."""
from contextlib import ExitStack
from datetime import timedelta, timezone
from pathlib import Path
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from interview_forge.api.app import app
from interview_forge.api.routers import private_archive
from interview_forge.services import auth


class PrivateArchiveTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.archive = self.root / 'private.zip'
        with zipfile.ZipFile(self.archive, 'w') as z:
            for name, content in {'index.html':'<html><head></head><body>PRIVATE_FIXTURE</body></html>',
                                  'assets/app.js':'window.fixture = 1;', 'data/history-data.json':'{"private":true}',
                                  'assets/media/image.webp':'private-image'}.items():
                z.writestr('site/' + name, content)
        self.db = self.root / 'auth.db'
        with self.connect() as db:
            db.executescript('''CREATE TABLE users(id INTEGER,username TEXT,role TEXT,is_active INTEGER,ai_daily_limit INTEGER,nickname TEXT,lang TEXT,last_seen TEXT);
            CREATE TABLE sessions(token TEXT,user_id INTEGER,expires_at TEXT);''')
            for i,(name,role,active,expiry) in enumerate([
                ('owner','admin',1,'2099-01-01'),('admin','admin',1,'2099-01-01'),
                ('reader','user',1,'2099-01-01'),('inactive','admin',0,'2099-01-01'),
                ('expired','admin',1,'2000-01-01')],1):
                db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(i,name,role,active,50,name,'java',''))
                db.execute('INSERT INTO sessions VALUES(?,?,?)',(auth._session_digest(name+'-token'),i,expiry))
        runtime=SimpleNamespace(AUTH_DB_PATH=self.db,now_iso=lambda:'2026-11-15T00:00:00',
                                _maybe_purge_sessions=lambda:None,SESSION_TTL=timedelta(days=30),time=time,BUSINESS_TZ=timezone.utc)
        self.stack.enter_context(patch.object(auth,'connect_auth',side_effect=self.connect))
        self.stack.enter_context(patch.object(auth,'server_runtime',runtime))
        self.stack.enter_context(patch('interview_forge.runtime.shared.enabled',return_value=False))
        self.stack.enter_context(patch.object(private_archive,'server_runtime',SimpleNamespace(PERMANENT_ADMIN_USERNAME='owner')))
        self.stack.enter_context(patch.dict('os.environ',{'INTERVIEW_FORGE_PRIVATE_ARCHIVE':str(self.archive)}))
        self.client = self.stack.enter_context(TestClient(app))

    def connect(self):
        db=sqlite3.connect(self.db);db.row_factory=sqlite3.Row;return db

    def request(self,path,token=None,method='GET'):
        self.client.cookies.clear()
        return self.client.request(method,path,headers={'Cookie':'forge_session='+token} if token else {})

    def test_every_resource_requires_permanent_admin_session(self):
        for path in ['/api/private-archive-status','/api/private-archive/index.html',
                     '/api/private-archive/assets/app.js','/api/private-archive/data/history-data.json',
                     '/api/private-archive/assets/media/image.webp']:
            for token,status in [(None,401),('forged',401),('reader-token',403),('admin-token',403),
                                 ('inactive-token',401),('expired-token',401),('owner-token',200)]:
                for method in ['GET','HEAD'] if 'status' not in path else ['GET']:
                    with self.subTest(path=path,token=token,method=method):
                        response=self.request(path,token,method)
                        self.assertEqual(response.status_code,status)
                        self.assertIn('no-store',response.headers['cache-control'])
                        if status!=200:self.assertNotIn('PRIVATE_FIXTURE',response.text)

    def test_revocation_and_role_changes_apply_on_next_request(self):
        self.assertEqual(self.request('/api/private-archive/index.html','owner-token').status_code,200)
        with self.connect() as db:db.execute("UPDATE users SET role='user' WHERE username='owner'")
        self.assertEqual(self.request('/api/private-archive/index.html','owner-token').status_code,403)
        with self.connect() as db:db.execute("DELETE FROM sessions")
        self.assertEqual(self.request('/api/private-archive/data/history-data.json','owner-token').status_code,401)

    def test_missing_configuration_and_public_repo_paths_fail_closed(self):
        for location in ['',str(private_archive.ROOT/'index.html'),'relative.zip']:
            with patch.dict('os.environ',{'INTERVIEW_FORGE_PRIVATE_ARCHIVE':location}):
                self.assertEqual(self.request('/api/private-archive/index.html','owner-token').status_code,503)
        with patch.object(private_archive,'server_runtime',SimpleNamespace(PERMANENT_ADMIN_USERNAME='')):
            self.assertEqual(self.request('/api/private-archive/index.html','owner-token').status_code,403)

    def test_traversal_unknown_files_and_conditional_requests(self):
        for path in ['data/%252e%252e/index.html','assets/../../private.zip','data/missing.json','assets/file.py','data//test.json']:
            response=self.request('/api/private-archive/'+path,'owner-token')
            self.assertNotEqual(response.status_code,200)
            self.assertNotIn('PRIVATE_FIXTURE',response.text)
        response=self.client.get('/api/private-archive/index.html',headers={'Cookie':'forge_session=owner-token','If-None-Match':'*'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('etag',response.headers)

    def test_only_html_integration_changes_archive_bytes(self):
        response=self.request('/api/private-archive/index.html','owner-token')
        self.assertIn('/assets/private-archive-theme.css',response.text)
        with zipfile.ZipFile(self.archive) as z:
            for name in ['assets/app.js','data/history-data.json','assets/media/image.webp']:
                self.assertEqual(self.request('/api/private-archive/'+name,'owner-token').content,z.read('site/'+name))
        self.assertEqual(self.request('/api/private-archive/index.html','owner-token','HEAD').content,b'')
