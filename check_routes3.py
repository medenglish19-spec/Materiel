from web.main import create_app
app = create_app()
paths = set()
for route in app.routes:
    path = getattr(route, 'path', None)
    if path:
        print(path)