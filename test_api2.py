import sys
sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from web.main import create_app
import json

app = create_app()
client = TestClient(app)

# Login first
response = client.post('/login', data={'username': 'admin', 'password': 'Admin@123'})
print('Login:', response.status_code)

# Test the API endpoint
response = client.get('/api/maintenance/operations', cookies=response.cookies)
print('Operations:', response.status_code)
data = response.json()
print('First operation:')
print(json.dumps(data[0], ensure_ascii=False, indent=2))