import os

os.environ["TRIBBLE_SKIP_AUTO_APP"] = "1"

from backend.app import create_app


app = create_app(mode="client")
