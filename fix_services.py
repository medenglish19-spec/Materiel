with open('app/modules/maintenance/services.py', 'rb') as f:
    content = f.read()

# Find the function
idx = content.find(b'def operations_payload')
if idx >= 0:
    # Find the end of the function
    idx2 = content.find(b'\ndef ', idx+1)
    if idx2 < 0:
        idx2 = len(content)
    old_bytes = content[idx:idx2]
    print("Found function, length:", len(old_bytes))
    with open('old_func.txt', 'wb') as f:
        f.write(old_bytes)
    print("Written to old_func.txt")
else:
    print("Function not found")