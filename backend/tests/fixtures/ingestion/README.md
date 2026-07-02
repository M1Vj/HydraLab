# Ingestion Fixture Corpus

Offline fixture corpus for `backend/tests/test_ingestion.py`.

- `instruction-injection.md`: direct instruction-shaped text that must remain `untrusted-external`.
- `auto-source-payload.html`: browser/document text attempting a consequential source/task write without a user trigger.
- `sample-paper.pdf`: lightweight PDF-shaped fixture used for local parser fallback tests.

Binary hostile archives are generated inside the tests so compression ratios and traversal paths are explicit in the test body.
