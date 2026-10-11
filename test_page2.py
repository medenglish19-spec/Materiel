import requests
import sys
sys.stdout.reconfigure(encoding='utf-8')

session = requests.Session()
resp = session.post('http://127.0.0.1:8000/login', data={'username': 'admin', 'password': 'Admin@123'})
resp = session.get('http://127.0.0.1:8000/maintenance/rules')

# Look for the specific operationsBody click handler
idx = resp.text.find("operationsBody')")
if idx >= 0:
    print(f"Found operationsBody at index {idx}")
    # Show surrounding context
    start = max(0, idx - 200)
    end = min(len(resp.text), idx + 500)
    print(resp.text[start:end])
else:
    print("operationsBody not found in expected form")

# Look for all occurrences
idx = resp.text.find("operationsBody")
while idx >= 0:
    print(f"\nFound at index {idx}:")
    start = max(0, idx - 100)
    end = min(len(resp.text), idx + 200)
    print(resp.text[start:end])
    idx = resp.text.find("operationsBody", idx + 1)