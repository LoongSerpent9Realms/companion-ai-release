"""
Plugin template - copy this folder and edit to create your own plugin.

Available API methods (api object is passed to on_load and on_message):
    api.read_data(key, default)   - read plugin-private JSON data
    api.write_data(key, value)    - write plugin-private JSON data
    api.read_shared(key, default) - read shared data (memory, training, etc.)
    api.data_dir()                - get plugin's data/ directory path
    api.log(message)              - print to console with plugin prefix
"""

name = "My Plugin"
description = "Describe what this plugin does"
version = "1.0.0"
buttons = [
    {"label": "My Button", "command": "/mycommand"},
]


def on_load(api):
    """Called when the plugin is loaded at startup."""
    api.log("loaded")


def on_unload():
    """Called when the plugin is unloaded."""
    pass


def on_message(message, api):
    """Called for every chat message.

    Return {"reply": "..."} to handle the message,
    or return None to let other plugins / built-in handlers process it.
    """
    if message == "/mycommand":
        return {"reply": "Hello from my plugin!"}
    return None
