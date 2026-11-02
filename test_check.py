from fastapi.testclient import TestClient
from web.main import create_app
import re

app = create_app()
client = TestClient(app)

response = client.post('/login', data={'username': 'admin', 'password': 'Admin@123'})
response = client.get('/maintenance/rules')
text = response.text

checks = [
    ('managementBtn', 'managementBtn'),
    ('managementMenu', 'managementMenu'),
    ('filter models', 'data-filter-col="models"'),
    ('operationModels', 'id="operationModels"'),
    ('groupFilter hidden', 'id="groupFilter"'),
    ('statusFilter hidden', 'id="statusFilter"'),
]

for name, check in checks:
    print(name + ':', check in text)

# Check operationModels has options
match = re.search(r'id="operationModels"[^>]*>(.*?)</select>', text, re.DOTALL)
if match:
    options = match.group(1).count('<option')
    print(f'operationModels options count: {options}')