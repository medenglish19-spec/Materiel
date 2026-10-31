with open('app/modules/maintenance/router.py', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('@router.delete("/api/maintenance/operation-groups/{group_id}"')
if idx >= 0:
    idx2 = content.find('@router.delete("/api/maintenance/operations/{operation_id}"', idx)
    if idx2 >= 0:
        snippet = content[idx:idx2]
        with open('snippet.txt', 'w', encoding='utf-8') as f:
            f.write(snippet)
        print("Written to snippet.txt, length:", len(snippet))