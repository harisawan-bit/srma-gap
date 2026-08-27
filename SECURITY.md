# Security Policy

## Supported Versions

The latest released version of `srma-gap` receives security fixes.

| Version | Supported |
| ------- | --------- |
| 1.0.x   | ✅        |

## Reporting a Vulnerability

If you discover a security issue, please **do not open a public GitHub issue**.

Instead, report it privately:

- Open a private security advisory on the repository
  ([GitHub Security Advisories](https://github.com/harisawan-bit/srma-gap/security/advisories/new)), or
- Contact the maintainer via a GitHub direct message.

You can expect an acknowledgement within a few days. Once the issue is
confirmed, a fix will be prepared on a private branch and shipped in a patch
release, after which the disclosure will be coordinated with the reporter.

## Scope notes

`srma-gap` is a read-only, dependency-free tool that queries public registries
(PubMed E-utilities and the PROSPERO API) over HTTPS. It does not accept
untrusted input beyond a topic string that is URL-encoded before being sent as
a query parameter, and it never executes remote code or writes outside the
terminal. Report anything that breaks that posture.
