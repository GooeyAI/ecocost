"""List Gooey's live LLMs that ecocost can't estimate.

Reads the AIModelSpec changelist from Gooey's Django admin (read-only) and
resolves every non-deprecated LLM's ``model_id`` against the knowledge base
in this checkout, the same lookup ``ecocost.estimate`` does.

The admin sits behind Cloudflare Access, which 403s Python's urllib, so the
requests go through curl with a cookie jar. Credentials come from the
environment (or ``--env-file``):

    CF_ACCESS_CLIENT_ID, CF_ACCESS_CLIENT_SECRET,
    GOOEY_ADMIN_USERNAME, GOOEY_ADMIN_PASSWORD

    python scripts/gooey_coverage.py --env-file ../gooey-server/.env

Prints one JSON object: ``missing`` (models with no ecocost record) and
``covered`` (model_id -> ecocost record id). Exits 1 when anything is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecocost.errors import UnknownModelError  # noqa: E402
from ecocost.loader import get_kb  # noqa: E402

ADMIN = "https://admin.gooey.ai"
LLM_CATEGORY = 3  # AIModelSpec.Categories.llm
FIELDS = ("name", "label", "creator", "model_id", "is_deprecated", "created_at")


class _Changelist(HTMLParser):
    """Rows of a Django admin changelist, as {field: text} keyed by column."""

    def __init__(self):
        super().__init__()
        self.rows: list[dict[str, str]] = []
        self._field: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr" and self._field is None:
            self._row: dict[str, str] = {}
        cls = a.get("class") or ""
        if tag in ("td", "th") and (m := re.search(r"field-(\w+)", cls)):
            self._field = m.group(1)
            self._row[self._field] = ""
        if tag == "img" and self._field:
            self._row[self._field] += a.get("alt") or ""
        if tag == "a" and self._field == "name" and a.get("href"):
            self._row["admin_id"] = a["href"].split("/")[3]

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._field = None
        if tag == "tr" and getattr(self, "_row", None):
            self.rows.append({k: v.strip() for k, v in self._row.items()})
            self._row = {}

    def handle_data(self, data):
        if self._field:
            self._row[self._field] += data


def _load_env(path: str):
    for line in Path(path).read_text().splitlines():
        if m := re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*)", line):
            os.environ.setdefault(m.group(1), m.group(2).strip().strip("'\""))


def _curl(jar: str, url: str, *data: str) -> str:
    cmd = ["curl", "-sf", "-c", jar, "-b", jar, "-e", url]
    for h in ("Id", "Secret"):
        cmd += [
            "-H",
            f"CF-Access-Client-{h}: {os.environ[f'CF_ACCESS_CLIENT_{h.upper()}']}",
        ]
    for d in data:
        cmd += ["--data-urlencode", d]
    return subprocess.run(
        cmd + [url], check=True, capture_output=True, text=True
    ).stdout


def fetch_llm_specs() -> list[dict[str, str]]:
    with tempfile.NamedTemporaryFile(suffix=".jar") as jar:
        page = _curl(jar.name, f"{ADMIN}/login/")
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
        _curl(
            jar.name,
            f"{ADMIN}/login/",
            f"csrfmiddlewaretoken={token}",
            f"username={os.environ['GOOEY_ADMIN_USERNAME']}",
            f"password={os.environ['GOOEY_ADMIN_PASSWORD']}",
        )
        html = _curl(
            jar.name,
            f"{ADMIN}/ai_models/aimodelspec/?all=&category__exact={LLM_CATEGORY}&o=-6",
        )
    if "field-model_id" not in html:
        sys.exit("admin login failed: no changelist in the response")
    parser = _Changelist()
    parser.feed(html)
    return [r for r in parser.rows if "model_id" in r]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--env-file", help="read credentials from this .env file")
    args = ap.parse_args()
    if args.env_file:
        _load_env(args.env_file)

    kb = get_kb()
    missing, covered = [], {}
    for spec in fetch_llm_specs():
        if spec.get("is_deprecated") == "True":
            continue
        try:
            covered[spec["model_id"]] = kb.resolve_model(spec["model_id"]).id
        except UnknownModelError as e:
            missing.append(
                {k: spec.get(k, "") for k in ("admin_id", *FIELDS)}
                | {"suggestions": e.suggestions}
            )
    json.dump({"missing": missing, "covered": covered}, sys.stdout, indent=2)
    print()
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
