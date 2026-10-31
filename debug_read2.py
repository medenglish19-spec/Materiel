with open('app/modules/maintenance/router.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('@router.delete("/api/maintenance/operation-groups/{group_id}"')
if idx >= 0:
    # Get the exact text between the two delete endpoints
    idx2 = content.find('@router.delete("/api/maintenance/operations/{operation_id}"', idx)
    if idx2 >= 0:
        print("Found both!")
        print("Length:", idx2 - idx)
        # Show with visible whitespace
        snippet = content[idx:idx2]
        snippet = snippet.replace(' ', '·').replace('\t', '→').replace('\n', '¶\n')
        print(snippet[:500])