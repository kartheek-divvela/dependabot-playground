def create_app(config=None):
    """Return a tiny Flask-like application stub."""
    return {"config": config or {}, "name": "module-a"}

def health():
    return {"status": "ok"}
