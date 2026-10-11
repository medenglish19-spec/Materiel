with open('snippet.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# Show with visible whitespace
for i, line in enumerate(content.splitlines(True)):
    line = line.rstrip('\n\r')
    visible = line.replace(' ', '·').replace('\t', '→')
    print(f"{i+1:3}: {visible} ({len(line)} chars)")