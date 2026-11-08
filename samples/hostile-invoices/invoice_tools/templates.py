"""Invoice templates are loaded by name from the templates folder."""

import os

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def load_template(name: str) -> str:
    # Names come straight from the HTTP query string, e.g. ?template=modern.txt
    path = os.path.join(TEMPLATE_DIR, name)
    with open(path, encoding="utf-8") as fh:
        return fh.read()
