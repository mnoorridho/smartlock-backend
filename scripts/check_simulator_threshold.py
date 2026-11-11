"""Real HTTP checks on a temporary virtual device; existing phone test data is preserved."""
import json
from pathlib import Path
import secrets
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ORIGIN = 'http://127.0.0.1:8000'

def call(method, path, body=None, token=None, form=False, expected=200):
    headers = {'Content-Type': 'application/x-www-form-urlencoded' if form else 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = (urlencode(body) if form else json.dumps(body)).encode() if body is not None else None
    try:
        with urlopen(Request(ORIGIN + path, data=data, headers=headers, method=method), timeout=10) as response:
            status, raw = response.status, response.read()
    except HTTPError as error:
        status, raw = error.code, error.read()
    assert status == expected, (method, path, status, raw[:200])
    return json.loads(raw) if raw else None

info = call('GET', '/local-test/info')
assert info['mode'] == 'local-test' and info['simulator_enabled'] and not info['hardware_commands_enabled']
saved = json.loads((Path(__file__).resolve().parent.parent / '.local/phone-test-accounts.json').read_text())
tokens = {}
for role in ('owner', 'user'):
    account = saved['accounts'][role]
    tokens[role] = call('POST', '/auth/login', {'username': account['email'], 'password': account['password']}, form=True)['access_token']
device_id = None
try:
    device = call('POST', '/devices/', {'device_code': 'SIM-CHECK-' + secrets.token_hex(4), 'name': 'Temporary simulator check', 'latitude': -7, 'longitude': 110, 'geofence_radius_m': 100}, tokens['owner'], expected=201)
    device_id = device['id']
    base = '/devices/' + device_id
    call('PATCH', base + '/face-verification', token=tokens['owner'])
    call('PATCH', base + '/access-schedule', {'enabled': False, 'start_time': '07:00', 'end_time': '17:00'}, tokens['owner'])
    permission = call('POST', '/permissions/', {'device_id': device_id, 'user_email': saved['accounts']['user']['email'], 'allow_face': True, 'allow_quick': False}, tokens['owner'], expected=201)
    policy = '/permissions/' + permission['id']
    call('PATCH', policy, {'face_match_threshold': .38}, tokens['owner'])
    call('PATCH', policy, {'face_match_threshold': .55}, tokens['user'], expected=403)
    call('PATCH', policy, {'face_match_threshold': .56}, tokens['owner'], expected=422)
    inside = {'latitude': -7, 'longitude': 110, 'accuracy_m': 10}
    allowed = call('POST', base + '/face-precheck', inside, tokens['user'])
    assert allowed['face_match_threshold'] == .38
    call('POST', base + '/face-precheck', {**inside, 'latitude': -7.1}, tokens['user'], expected=403)
    call('POST', base + '/face-precheck', {**inside, 'accuracy_m': 500}, tokens['user'], expected=400)
    call('POST', base + '/quick-unlock', token=tokens['user'], expected=403)
    for _ in range(10):
        state = call('GET', base, token=tokens['user'])
        if state['status'] == 'online': break
        time.sleep(.2)
    assert state['simulated'] and state['status'] == 'online'
    command = call('POST', base + '/unlock', {**inside, 'face_verified': True}, tokens['user'])
    assert command['status'] == 'command_sent' and command['simulated']
    for _ in range(20):
        ack = call('GET', base + '/commands/' + command['transaction_id'], token=tokens['user'])
        if ack['result'] == 'success': break
        time.sleep(.2)
    assert ack['result'] == 'success' and ack['simulated']
    assert call('GET', base, token=tokens['user'])['lock_status'] == 'unlocked'
    logs = call('GET', base + '/logs', token=tokens['user'])
    assert any(log['result'] == 'success' and '[SIMULASI]' in log['note'] for log in logs)
    for _ in range(35):
        if call('GET', base, token=tokens['user'])['lock_status'] == 'locked': break
        time.sleep(.2)
    assert call('GET', base, token=tokens['user'])['lock_status'] == 'locked'
    print('PASS: online heartbeat, GPS denials, method permission, owner-only bounded threshold, exact simulated ACK, success audit and automatic relock.')
finally:
    if device_id:
        call('DELETE', '/devices/' + device_id, token=tokens['owner'], expected=204)
        print('Temporary check device removed; existing devices, faces and GPS were preserved.')
