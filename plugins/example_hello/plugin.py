"""Example plugin: responds to /hello and tracks visit count."""

name = "Hello Plugin"
description = "Example plugin - responds to /hello and tracks visit count"
version = "1.0.0"
buttons = [
    {"label": "Say Hello", "command": "/hello"},
    {"label": "Visit Count", "command": "/hello_count"},
]

_api = None


def on_load(api):
    global _api
    _api = api
    # initialise counter if first time
    if api.read_data("counter") is None:
        api.write_data("counter", 0)
    api.log("loaded!")


def on_unload():
    _api.log("unloaded")


def on_message(message, api):
    if message == "/hello":
        n = api.read_data("counter", 0) + 1
        api.write_data("counter", n)
        return {"reply": f"Hello! You've visited {n} time(s)."}

    if message == "/hello_count":
        n = api.read_data("counter", 0)
        return {"reply": f"Visit count: {n}"}

    return None  # pass through to built-in handlers
