# Security Policy

## Reporting a vulnerability

Please report security issues **privately**, not as a public issue or pull
request.

Use GitHub's [private vulnerability
reporting](https://github.com/CesarBallardini/python-kl1/security/advisories/new)
on this repository. If that is unavailable to you, contact the maintainer
through the address on the [GitHub profile](https://github.com/CesarBallardini).

Please include, as far as you can:

- what the issue is and which component it affects;
- the steps or a minimal case that reproduces it;
- the impact you think it has;
- the version or commit you observed it on.

You can expect an acknowledgement within **7 days** and an assessment within
**30 days**. If the report is accepted, the fix and a disclosure timeline get
agreed with you before anything is published; credit is given unless you would
rather it were not.

## Scope

python-kl1 is a **pure library** with no runtime dependencies: an in-process
scheduler, logic variables and a clause DSL, with no network, storage or
authentication surface of its own. In practice the security-relevant surface is
the supply chain and the CI configuration:

- a dependency in `uv.lock`;
- a GitHub Actions workflow, a composite action, or a pinned action digest;
- a pre-commit hook definition;
- a secret accidentally committed to the history.

Reports about those are very much in scope, as is a way to make the library run
code it was not given (for example through a crafted term).

## Supported versions

The newest release is the supported one. Fixes go to `main` and land in the
next tag rather than being backported.

## How this repository defends itself

| Concern | Tool |
| --- | --- |
| Vulnerable dependencies | `pip-audit` and OSV-Scanner, over `uv.lock` |
| Insecure code patterns | `bandit` |
| Committed secrets | `gitleaks`, as a hook and over the whole tree in CI |
| Dependency freshness | Dependabot, weekly, with a 10-day cooldown |
| Supply-chain posture | OpenSSF Scorecard |
| Workflow tampering | every action pinned to a commit digest; `permissions: {}` by default |
| License obligations | `pip-licenses`, gating the distributed dependencies |
