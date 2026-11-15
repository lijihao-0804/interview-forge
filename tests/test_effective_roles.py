"""All identities and sessions in this file are synthetic and isolated."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import re
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from interview_forge.api.app import app
from interview_forge.core.roles import effective_role, role_fields
from interview_forge.core.runtime import server_runtime
from interview_forge.services import auth, gym, registration


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("IF_TURNSTILE_SITE_KEY", "")
    monkeypatch.setenv("IF_TURNSTILE_SECRET", "")
    with patch.dict(server_runtime._values, {
        "AUTH_DB_PATH": tmp_path / "auth.db", "USERS_DIR": tmp_path / "users",
        "_AUTH_READY": False, "PERMANENT_ADMIN_USERNAME": "OwnerFixture",
    }), patch("interview_forge.runtime.shared.enabled", return_value=False), \
            patch.object(gym, "send_email") as mail:
        people = {name: auth.create_user(name, "fixture-password", role=role,
                    email=name.lower() + "@example.test")
                  for name, role in [("OwnerFixture", "admin"), ("AdminFixture", "admin"), ("UserFixture", "user")]}
        yield people, mail


def test_role_is_derived_not_client_supplied():
    for role, active, configured, username, expected in [
        ("admin", 1, "owner", "owner", "super_admin"),
        ("admin", 1, "", "owner", "admin"),
        ("admin", 0, "owner", "owner", "user"),
        ("admin", 1, "owner", "Owner", "admin"),
        ("user", 1, "owner", "owner", "user"),
        ("super_admin", 1, "owner", "owner", "user"),
    ]:
        person = {"role": role, "is_active": active, "username": username, "effective_role": "super_admin"}
        assert effective_role(person, permanent_username=configured) == expected
    assert effective_role({"role": "admin", "username": "owner"}, permanent_username="owner") == "admin"
    assert effective_role(None, permanent_username="owner") == "user"


@pytest.mark.parametrize("name,tier,status", [("OwnerFixture", "super_admin", 200),
    ("AdminFixture", "admin", 403), ("UserFixture", "user", 403)])
def test_login_me_admin_and_private_resources(accounts, name, tier, status):
    with patch('interview_forge.api.routers.private_archive._read_member', return_value=b'<html>fixture</html>'), \
            TestClient(app, raise_server_exceptions=False) as client:
        result = client.post('/api/login', json={'username': name.lower()+'@example.test', 'password':'fixture-password',
                                                'role':'super_admin','effective_role':'super_admin'})
        assert result.status_code == 201
        assert result.json()['effective_role'] == tier
        assert result.json()['role'] == ('user' if tier == 'user' else 'admin')
        assert client.get('/api/me').json()['effective_role'] == tier
        assert client.get('/pages/admin.html', follow_redirects=False).status_code == (403 if tier == 'user' else 200)
        for path in ('index.html', 'data/manifest.json', 'assets/app.js'):
            for method in ('GET', 'HEAD'):
                response = client.request(method, '/api/private-archive/' + path)
                assert response.status_code == status
                assert 'no-store' in response.headers['cache-control']


def test_existing_session_rechecks_config_active_role_and_tampering(accounts):
    token = auth.create_session(accounts[0]['OwnerFixture']['id'])
    with TestClient(app, raise_server_exceptions=False) as client, \
            patch('interview_forge.api.routers.private_archive._read_member', return_value=b'fixture'):
        client.cookies.set('forge_session', token)
        assert client.get('/api/me').json()['effective_role'] == 'super_admin'
        with patch.dict(server_runtime._values, {'PERMANENT_ADMIN_USERNAME': ''}):
            assert client.get('/api/me').json()['effective_role'] == 'admin'
            assert client.get('/api/private-archive/index.html').status_code == 403
        with closing(auth.connect_auth()) as db:
            db.execute("UPDATE users SET role='user' WHERE username='OwnerFixture'")
        assert client.get('/api/me').json()['effective_role'] == 'user'
        assert client.get('/api/private-archive/data/manifest.json').status_code == 403
        with closing(auth.connect_auth()) as db:
            db.execute("UPDATE users SET is_active=0 WHERE username='OwnerFixture'")
        assert client.get('/api/me').status_code == 401
        client.cookies.clear()
        assert client.get('/api/private-archive/index.html', headers={'Cookie':'forge_session=super_admin'}).status_code == 401


def test_initializer_never_promotes_and_admin_cannot_modify_owner(accounts):
    with closing(auth.connect_auth()) as db:
        db.execute("UPDATE users SET role='user' WHERE username='OwnerFixture'")
    with patch.dict(server_runtime._values, {'_AUTH_READY': False}):
        with closing(auth.connect_auth()) as db:
            assert db.execute("SELECT role FROM users WHERE username='OwnerFixture'").fetchone()[0] == 'user'
    for operation in [lambda: auth.set_user_role('OwnerFixture','admin','AdminFixture'),
                      lambda: auth.set_user_role('OwnerFixture','super_admin','AdminFixture'),
                      lambda: auth.reset_user_password('OwnerFixture','new-password','AdminFixture'),
                      lambda: auth.reset_user_nickname('OwnerFixture','AdminFixture'),
                      lambda: auth.set_user_active('OwnerFixture',False)]:
        with pytest.raises(ValueError): operation()
    with pytest.raises(ValueError): auth.create_user('Injected', 'fixture-password', role='super_admin')
    # Ordinary administrators keep the existing ability to manage other users.
    assert auth.set_user_role('UserFixture','admin','AdminFixture')['role'] == 'admin'
    assert effective_role(auth.auth_login('UserFixture','fixture-password')) == 'admin'


@pytest.mark.parametrize('failure',[gym.SMTPNotConfiguredError('fixture'), OSError('fixture failure')])
def test_recovery_delivery_failures_have_same_public_ack(accounts, failure):
    accounts[1].side_effect = failure
    with TestClient(app, raise_server_exceptions=False) as client, \
            patch('interview_forge.api.routers.auth.send_password_reset_code', side_effect=registration.send_password_reset_code):
        unknown = client.post('/api/password/forgot/send-code',json={'email':'unknown@example.test'})
        known = client.post('/api/password/forgot/send-code',json={'email':'userfixture@example.test'})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    with closing(auth.connect_auth()) as db:
        assert db.execute("SELECT COUNT(*) FROM registration_email_codes WHERE status IN ('active','pending')").fetchone()[0] == 0


def test_http_recovery_does_not_wait_for_account_lookup_or_delivery(accounts):
    with ThreadPoolExecutor(max_workers=1) as request_pool, \
            patch('interview_forge.api.routers.auth.registration_email_executor', request_pool), \
            patch.object(registration.registration_email_executor, 'submit') as queued, \
            patch.object(registration, '_active_user_by_email', side_effect=AssertionError('lookup before acknowledgement')), \
            TestClient(app, raise_server_exceptions=False) as client:
        unknown = client.post('/api/password/forgot/send-code',json={'email':'unknown@example.test'})
        known = client.post('/api/password/forgot/send-code',json={'email':'userfixture@example.test'})
        assert unknown.status_code == known.status_code == 200
        assert unknown.json() == known.json()
        assert queued.call_count == 2
        jobs = list(queued.call_args_list)
        accounts[1].assert_not_called()
    # Run the queued synthetic jobs only after both acknowledgements exist.
    accounts[1].side_effect = gym.SMTPNotConfiguredError('fixture')
    for job in jobs:
        job.args[0](*job.args[1:])
    assert accounts[1].call_count == 1
    with closing(auth.connect_auth()) as db:
        assert db.execute("SELECT COUNT(*) FROM registration_send_attempts").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM registration_email_codes WHERE status IN ('active','pending')").fetchone()[0] == 0


def test_registration_payload_cannot_grant_privileges(accounts):
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/register/send-code',json={'email':'new@example.test'})
        assert response.status_code == 200
        code = re.search(r'验证码：(\d{6})', accounts[1].call_args.args[2]).group(1)
        response = client.post('/api/register',json={'email':'new@example.test','code':code,'username':'NewFixture',
                              'password':'fixture-password','role':'admin','effective_role':'super_admin'})
        assert response.status_code == 201
        assert response.json()['role'] == response.json()['effective_role'] == 'user'
