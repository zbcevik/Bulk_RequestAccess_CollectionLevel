# Contributing

1. Fork the repository and create a focused feature branch.
2. Use only artificial data in tests, fixtures, examples, and documentation.
3. Never commit API tokens, credentials, local configuration, production
   metadata, generated dataset exports, or machine-specific paths.
4. Install development dependencies with
   `python3 -m pip install -r requirements-dev.txt`.
5. Run `python3 -m pytest` and `python3 -m ruff check .`.
6. Confirm preview mode makes no network updates and mock all HTTP requests in
   automated tests.
7. Submit a pull request describing the behaviour change, safety impact,
   validation performed, and any documentation changes.

Changes to update or push behaviour require tests for success, invalid input,
and failure paths. Keep the three supported JSON shapes consistent:
`files`, `latestVersion.files`, and `datasetVersion.files`.
