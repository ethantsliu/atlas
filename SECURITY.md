# Security policy

## Supported version

Security fixes are applied to the current `main` branch. This research data project
does not maintain separate supported release lines.

The scheduled anonymous live probe checks release reachability and content-addressed
asset integrity. It sends no credential, cookie, account identifier, or visitor data.

## Reporting a vulnerability

Please use GitHub's private vulnerability-reporting feature for vulnerabilities,
credential exposure, or privacy leaks. Do not open a public issue containing a
secret, personal identifier, private path, unpublished artifact, or exploit that
would put a deployed instance at risk.

Include the affected revision, impact, a minimal reproduction, and any suggested
remediation. Maintainers will acknowledge a report when available, assess its scope,
and coordinate disclosure after a fix is ready. Research-record corrections that do
not involve security or privacy can use the normal contribution process.

## Deployment boundary

The browser receives only a Supabase publishable key and read-only data. Database
connection strings, elevated keys, and synchronization credentials are server-side
secrets. If one of those values reaches a tracked file, build log, issue, or browser
bundle, revoke it before treating redaction alone as remediation.
