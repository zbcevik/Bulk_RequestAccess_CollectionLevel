# Security policy

## Reporting a vulnerability

Do not disclose vulnerabilities, API tokens, private dataset metadata, or
credentials in a public issue. Use GitHub's private vulnerability reporting
feature for this repository when available, or contact the repository owner
through an approved private organizational channel.

Include the affected version or commit, reproduction steps using dummy data,
the potential impact, and any suggested mitigation. Do not test against a
production Dataverse instance without explicit authorization.

## Credential exposure

If a real token is committed or shared publicly, revoke or rotate it
immediately. Removing it from the newest commit is not sufficient because it
may remain in Git history and third-party caches.
