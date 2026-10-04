"""Start the local server: `devai serve PROJECT... [--port N]` (D051)."""

import threading
import webbrowser

import uvicorn

from devai.web.app import create_app, load_projects, web_dist
from devai.web.security import new_token

DEFAULT_PORT = 8765


def serve(paths: list[str], port: int, listen_all: bool, open_browser: bool) -> None:
    """Run until Ctrl+C. Raises NotADirectoryError for a path that isn't a folder.

    `listen_all` is for containers only: the container listens on all of its
    interfaces so Docker can forward the port, which compose publishes on the
    host's 127.0.0.1 alone.
    """
    projects = load_projects(paths)
    token = new_token()
    dist = web_dist()
    app = create_app(projects, token, dist)
    url = f"http://127.0.0.1:{port}/?token={token}"

    names = ", ".join(project.name for project in projects)
    print(f"DevAI is serving {names}, for this computer only.")
    print(f"Open: {url}")
    if not (dist / "index.html").is_file():
        print("(The pages aren't built yet: only the API answers.)")
    # flush: in a container or a pipe, stdout is buffered and the address
    # would stay hidden while the server runs.
    print(
        "Stop with Ctrl+C. The address changes every time: it holds the token.",
        flush=True,
    )
    if open_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()

    uvicorn.run(
        app,
        host="0.0.0.0" if listen_all else "127.0.0.1",  # 0.0.0.0: containers only
        port=port,
        log_level="warning",
        access_log=False,  # the first URL carries the token: never log it
    )
