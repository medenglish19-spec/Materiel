import requests
import sys
sys.stdout.reconfigure(encoding='utf-8')

session = requests.Session()
resp = session.post('http://127.0.0.1:8000/login', data={'username': 'admin', 'password': 'Admin@123'})
resp = session.get('http://127.0.0.1:8000/maintenance/rules')
print('Page status:', resp.status_code)

# Check for click handler on group cell
if 'data-group-id' in resp.text:
    print('OK: data-group-id attribute in table')
else:
    print('MISSING: data-group-id attribute in table')

# Check for operationsBody click handler
click_handlers = resp.text.count("operationsBody')")
print(f'operationsBody occurrences: {click_handlers}')

# Check for the click handler for group cell
if "groupCell" in resp.text:
    print('OK: groupCell variable in click handler')
else:
    print('MISSING: groupCell variable')

# Check for duplicate click handlers on operationsBody
count_click = resp.text.count("addEventListener('click'")
print(f'Total click handlers: {count_click}')

# Look for specific handlers
if "data-condition-details" in resp.text:
    print('OK: data-condition-details handler present')

# Find all click handlers
import re
handlers = re.findall(r"\.addEventListener\('click'.*?\)", resp.text)
print(f'Click handlers found: {len(handlers)}')
for h in handlers:
    if 'operationsBody' in h:
        print(f'  operationsBody: {h[:100]}...')
    elif 'conditionDetails' in h:
        print(f'  conditionDetails: {h[:100]}...')
    else:
        print(f'  Other: {h[:100]}...')