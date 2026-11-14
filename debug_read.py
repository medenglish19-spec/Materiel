with open('app/modules/maintenance/router.py', 'r', encoding='utf-8') as f:
    content = f.read()
idx = content.find('@router.delete("/api/maintenance/operation-groups/{group_id}"')
if idx >= 0:
    print(repr(content[idx:idx+500]))