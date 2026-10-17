import requests
import sys
sys.stdout.reconfigure(encoding='utf-8')

session = requests.Session()
resp = session.post('http://127.0.0.1:8000/login', data={'username': 'admin', 'password': 'Admin@123'})
resp = session.get('http://127.0.0.1:8000/maintenance/rules')

# Check if groupEditor is properly defined
if 'groupEditor' in resp.text and 'groupForm' in resp.text:
    print("Group editor elements present in HTML")

# Check if the group editor is hidden by default
if 'style="display:none"' in resp.text:
    print("Modal is hidden by default")

# Check the menu items
checks = [
    'menuNewGroup',
    'menuEditGroup',
    'menuDeleteGroup',
    'groupFilter',
]

for c in checks:
    if c in resp.text:
        print(f"  Found: {c}")
    else:
        print(f"  MISSING: {c}")

# Check the openGroupEditor function
if 'function openGroupEditor' in resp.text:
    print("openGroupEditor function present")
    
# Check the click handler for group cell
if 'data-group-id' in resp.text and 'groupCell' in resp.text:
    print("Group cell click handler present")

# Check if state.groups is loaded
if 'state.groups' in resp.text:
    print("state.groups referenced")

# Check the select element for groupFilter
import re
selects = re.findall(r'<select id="groupFilter".*?</select>', resp.text, re.DOTALL)
if selects:
    print(f"groupFilter select found, length: {len(selects[0])}")
    # Check if it has options
    options = re.findall(r'<option value="([^"]*)">([^<]*)</option>', selects[0])
    print(f"  Options: {options}")
else:
    print("groupFilter select NOT found in initial HTML (may be populated by JS)")

# Check the dropdown menu items
menu_items = re.findall(r'<button[^>]*id="menuNewGroup"[^>]*>.*?</button>', resp.text, re.DOTALL)
if menu_items:
    print(f"menuNewGroup button: {menu_items[0][:200]}")
else:
    print("menuNewGroup button NOT found")

menu_items = re.findall(r'<button[^>]*id="menuEditGroup"[^>]*>.*?</button>', resp.text, re.DOTALL)
if menu_items:
    print(f"menuEditGroup button: {menu_items[0][:200]}")
else:
    print("menuEditGroup button NOT found")