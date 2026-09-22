# Security

## Reporting a vulnerability

Please report security issues privately through GitHub's
[private vulnerability reporting](https://github.com/GooeyAI/ecocost/security/advisories/new),
not in a public issue or pull request. We aim to acknowledge reports within a
few working days.

## Scope

ecocost is a pure-Python library with no network access at runtime. Its data
files are parsed with `yaml.safe_load`, and every argument to `estimate` is
validated. Relevant reports include:

- a way to make `estimate` crash, hang or use excessive memory from its
  arguments;
- anything in the release pipeline (`.github/workflows/release.yml`) that could
  publish a package not built from this repository.

Wrong figures in `ecocost/data/` are not security issues; please open a pull
request or an issue for those (see [CONTRIBUTING.md](CONTRIBUTING.md)).
