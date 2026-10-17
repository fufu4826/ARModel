"""Run Flask against the local Wrangler D1 gateway without changing env files."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app

if __name__ == '__main__':
    app.config.update(D1_GATEWAY_URL='http://127.0.0.1:8787')
    app.run(host='127.0.0.1', port=5016, debug=False)
