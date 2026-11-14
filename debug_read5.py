with open('snippet.txt', 'rb') as f:
    content = f.read()

print(content[:200])
print("---")
for i, b in enumerate(content[:200]):
    if b >= 128:
        print(f"Byte {i}: {b} (0x{b:02x})")