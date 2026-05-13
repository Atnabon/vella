# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✓         |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report them privately by emailing:

**oliyadmilkessa@gmail.com**

Include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept (if safe to share)
- Any suggested fix (optional)

You can expect an acknowledgement within **72 hours** and a resolution timeline within **14 days** for critical issues.

## Scope

This project handles financial documents, API keys for third-party services (Anthropic, OpenAI, QuickBooks, Plaid), and user-uploaded files. Please pay particular attention to:

- Authentication and authorization bypasses
- Secrets or credentials leaking through API responses or logs
- File upload vulnerabilities (path traversal, malicious content)
- Injection attacks (SQL, prompt injection)
- Insecure deserialization

## Out of Scope

- Issues in third-party dependencies (report those upstream)
- Theoretical vulnerabilities with no practical attack path
- Issues requiring physical access to the server
