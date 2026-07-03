# Security Policy

## Supported versions

HydraLab is pre-release software. Only the latest code on `develop` and `main` is supported; there are no maintained release branches yet. If you find a vulnerability in an older commit, please verify it still reproduces on the tip of `develop` before reporting.

## Reporting a vulnerability

Please report vulnerabilities privately by email:

**interns@ai4gov.net**

Do **not** open a public GitHub issue for security problems — public disclosure before a fix is available puts users at risk.

Include what you can of the following:

- A description of the issue and its impact
- Steps to reproduce (a proof of concept is ideal)
- The commit hash you tested against
- Your environment (macOS version, Python/Bun versions)

## What to expect

This is a small pre-release project maintained on a best-effort basis. We aim to acknowledge reports within a few business days and to keep you informed as we investigate and fix confirmed issues. We do not currently run a bug bounty program, but we are happy to credit reporters in release notes if desired.

## Scope and threat model

HydraLab is a local-first application: the backend binds to 127.0.0.1 only, data stays on the user's machine, and secrets are stored in the OS keychain. Reports in the following areas are especially valuable:

- **Untrusted content handling.** HydraLab ingests documents (PDFs, papers) and web page content via the Chrome extension. Vulnerabilities where malicious document or page content can execute code, exfiltrate data, or corrupt the local database are in scope.
- **Provider egress.** Any path where data leaves the machine without an explicit user action — including unintended requests to model providers or other third parties — violates the project's core privacy promise and is treated as a security issue.
- **Secret handling.** Any way an API key or credential can end up outside the OS keychain (config files, logs, the SQLite database, crash reports) is in scope.
- **Local attack surface.** Issues exploitable by other local processes or users (e.g. weaknesses in the localhost API's exposure) are in scope, keeping in mind that HydraLab assumes a single trusted user on the machine.

Out of scope: issues requiring a fully compromised machine or root access, and vulnerabilities in third-party dependencies that have no exploitable path through HydraLab (though heads-ups about vulnerable dependencies are still appreciated).
