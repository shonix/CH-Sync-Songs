# Tests

The test suite uses Python's built-in `unittest` module, so no extra packages are required.

Run all tests from the repository root:

```powershell
python -m unittest discover -s tests
```

The suite includes:

- Unit tests for song metadata parsing, identity matching, folder naming, and duplicate planning.
- Integration-style tests for socket JSON framing and streamed zip transfer.
- Safety coverage for rejecting unsafe zip paths.
- CLI guard tests for destructive cleanup flags.

Temporary fixtures are created under the ignored `tests_tmp/` directory.
