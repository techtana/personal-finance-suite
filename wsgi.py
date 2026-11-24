"""Entry point for a production server: `waitress-serve --listen=127.0.0.1:8080 wsgi:app`.

Run exactly one process. The backup timer, the import worker and the queue of AI jobs
for the home runner all live in this process's memory; a second process would not see them.
"""

from app import create_app

app = create_app()
