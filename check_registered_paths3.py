with open('tests/test_navigation_and_routes.py', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('_registered_paths')
if idx != -1:
    with open('registered_paths_full2.txt', 'w', encoding='utf-8') as f:
        f.write(text[idx:idx+1000])
    print('Written')
else:
    print('Not found')