with open('app/modules/maintenance/services.py', 'rb') as f:
    content = f.read()

idx = content.find(b'def operations_payload')
if idx >= 0:
    idx2 = content.find(b'\r\n\ndef ', idx+1)
    if idx2 < 0:
        idx2 = len(content)
    old_bytes = content[idx:idx2]
    print(f"Found {len(old_bytes)} bytes")
    with open('old_bytes.bin', 'wb') as f:
        f.write(old_bytes)
    print("Written to old_bytes.bin")
else:
    print("Function not found")