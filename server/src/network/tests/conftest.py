import sys
import os

# Add server/src to sys.path so we can use absolute imports from backend/routes
server_src = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if server_src not in sys.path:
    sys.path.insert(0, server_src)
