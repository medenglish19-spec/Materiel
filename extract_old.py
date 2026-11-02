with open('app/modules/maintenance/router.py', 'rb') as f:
    content = f.read()

idx = content.find(b'@router.delete("/api/maintenance/operation-groups/{group_id}"')
idx2 = content.find(b'@router.delete("/api/maintenance/operations/{operation_id}"', idx)

old_bytes = content[idx:idx2]
print(f"Found {len(old_bytes)} bytes")
with open('old_bytes.bin', 'wb') as f:
    f.write(old_bytes)
print("Written to old_bytes.bin")