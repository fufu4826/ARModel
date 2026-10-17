"""Run a loopback-only review against cloud D1; never persists plaintext credentials."""
import argparse
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os

# A review preview must not add localhost page views to the database that will go live.
os.environ['ARMODEL_ANALYTICS_ENABLED'] = '0'

from scripts.prepare_cloud_d1 import stored_token
from app import app


def configure():
    target = tomllib.loads((Path.home() / '.armodel-secrets/d1-target.toml').read_text(encoding='utf-8'))
    app.config.update(D1_GATEWAY_URL='', D1_GATEWAY_TOKEN='', D1_ACCOUNT_ID=target['account_id'],
                      D1_DATABASE_ID=target['database_id'], D1_API_TOKEN=stored_token())
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=5017)
    args = parser.parse_args()
    configure().run(host='127.0.0.1', port=args.port, debug=False)
