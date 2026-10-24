import requests
import json
import sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

session = requests.Session()
resp = session.post('http://127.0.0.1:8000/login', data={'username': 'admin', 'password': 'Admin@123'})
print('Login status:', resp.status_code)

# Test GET operation groups
resp = session.get('http://127.0.0.1:8000/api/maintenance/operation-groups')
print('GET groups status:', resp.status_code)
groups = resp.json()
print('Number of groups:', len(groups))
for g in groups:
    name = g['name'].encode('ascii', 'replace').decode()
    print(f'  ID: {g["id"]}, Name: {name}, Sort: {g["sort_order"]}')

# Test POST - create group
print("\n--- Testing POST ---")
resp = session.post('http://127.0.0.1:8000/api/maintenance/operation-groups', json={'name': 'Test Group', 'sort_order': 99})
print('POST status:', resp.status_code)
if resp.status_code == 201:
    new_group = resp.json()
    name = new_group['name'].encode('ascii', 'replace').decode()
    print(f'Created: ID={new_group["id"]}, Name={name}')
else:
    print('Error:', resp.text)

# Test GET again
resp = session.get('http://127.0.0.1:8000/api/maintenance/operation-groups')
groups = resp.json()
print('\nGroups after POST:', len(groups))
for g in groups:
    name = g['name'].encode('ascii', 'replace').decode()
    print(f'  ID: {g["id"]}, Name: {name}, Sort: {g["sort_order"]}')

# Test PUT - update group
if len(groups) > 0:
    test_id = groups[-1]['id']
    print(f"\n--- Testing PUT on ID {test_id} ---")
    resp = session.put(f'http://127.0.0.1:8000/api/maintenance/operation-groups/{test_id}', json={'name': 'Updated Group', 'sort_order': 100})
    print('PUT status:', resp.status_code)
    if resp.status_code == 200:
        updated = resp.json()
        name = updated['name'].encode('ascii', 'replace').decode()
        print(f'Updated: ID={updated["id"]}, Name={name}')
    else:
        print('Error:', resp.text)

# Test DELETE
print(f"\n--- Testing DELETE on ID {test_id} ---")
resp = session.delete(f'http://127.0.0.1:8000/api/maintenance/operation-groups/{test_id}')
print('DELETE status:', resp.status_code)