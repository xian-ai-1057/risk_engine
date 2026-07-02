"""``python -m web`` → launch the uvicorn dev server.

Honours ``RISK_WEB_HOST`` / ``RISK_WEB_PORT`` (defaults 127.0.0.1:8000).
For production-style runs use ``uvicorn web.app:app`` directly.
"""
from web.app import main

if __name__ == "__main__":
    main()
