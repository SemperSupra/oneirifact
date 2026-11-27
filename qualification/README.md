# Delivery qualification fixtures

These standalone tests qualify two prerequisites for browser delivery. They contain no application engine or user data and are not part of the deployed showcase.

- Go WebAssembly in an ES module worker at a real static HTTP project base path; requires Go 1.23.2+, Python 3.10+ and Chrome/Chromium.
- Gitleaks 8.30.1 with supervisor-supplied rules and synthetic credentials generated only inside a temporary test directory; requires the pinned Linux x64 release binary.

Run `python3 qualification/worker_http.py` and `python3 qualification/scanner_probe.py /path/to/gitleaks` from the repository root. The public qualification workflow uses standard Ubuntu runners and does not deploy this branch. Results do not qualify application geometry, actual release content, hardware performance or guarantee absence of secrets.
