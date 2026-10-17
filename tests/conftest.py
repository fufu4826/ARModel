"""Test clients submit Admin forms the way a browser does: with the rendered data revisions."""
from flask.testing import FlaskClient

import app as module
from armodel.repositories.database import DatabaseError


class RevisionClient(FlaskClient):
    def open(self, *args, **kwargs):
        path = args[0] if args and isinstance(args[0], str) else kwargs.get("path", "")
        if (kwargs.get("method") == "POST" and path.startswith("/admin/") and path != "/admin/login"
                and kwargs.get("json") is None and not kwargs.pop("omit_revisions", False)):
            data = kwargs.get("data")
            data = {} if data is None else data
            if isinstance(data, dict):
                try:
                    versions = module.get_database().batch([("SELECT name,version FROM dataset_versions", [])])[0]
                except DatabaseError:
                    versions = []
                kwargs["data"] = {**{f"revision_{row['name']}": str(row["version"]) for row in versions}, **data}
        kwargs.pop("omit_revisions", None)
        return super().open(*args, **kwargs)


module.app.test_client_class = RevisionClient
