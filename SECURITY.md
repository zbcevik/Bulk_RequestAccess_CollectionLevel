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

Store Dataverse tokens only in the ignored `config.ini` file and restrict that
file to the local user with `chmod 600 config.ini`. Never paste tokens into an
issue, pull request, commit message, Actions log, screenshot, or command-line
`--api-key` argument.

## Repository and account settings

For a public GitHub repository, the maintainer should enable:

- two-factor authentication (preferably a passkey or hardware security key);
- branch protection or a ruleset requiring pull requests and passing CI;
- GitHub secret scanning and push protection when available;
- Dependabot alerts and security updates;
- private vulnerability reporting.

Use a personal access token only when GitHub requires one. Give it the minimum
repository scope, set an expiry date, and delete unused tokens and SSH keys from
GitHub account settings. The Gitleaks, CodeQL, and CI workflows in this
repository should remain enabled; they use narrowly scoped automatic Actions
credentials and do not read the local `config.ini` file.
