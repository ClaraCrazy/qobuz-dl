# Dependency automation

Dependabot proposes updates daily. The agent owns technical review and fixes; the user is not expected to review dependency PRs.

Stable compatible dependency updates may merge after meaningful CI succeeds at the exact PR head, every other check completes successfully, and the branch is current. Each run merges at most one PR. Existing deployment integration runs only after those checks.

Major versions, pre-1.0 minor changes, maintainer changes, unusual versions and workflow edits require the agent to examine upstream changes and actual application usage. The agent records compatibility evidence in the administrator-controlled `DEPENDENCY_REVIEWS` repository variable. This JSON uses schema 1 and a `reviews` array; each entry binds `pr`, `head`, `base`, `compatibility: "verified"`, a substantive `rationale`, HTTPS `evidence` links, and `allowedFiles`. A review cannot substitute for CI. Workflow exceptions apply only to named existing workflow files; application-source migrations need separate tested commits.

Missing or failing CI, unresolved migrations, custom source changes and explicit hold labels are technical blockers for the agent to resolve. They are not a human review queue. Rebased or edited commits invalidate the recorded review.

Set `DEPENDENCY_AUTOMATION_PAUSED=true` to pause merging. Manual workflow dispatch defaults to audit; schedules and completed CI can apply eligible updates. Privileged merge workflows never check out or run PR code.

Required CI builds and installs the wheel on Linux and Windows with Python 3.11 and 3.13. Eleven runtime tests exercise the actual HTTP metadata transport against a loopback fixture, pagination, rejected authentication and ineligible-account responses, SQLite persistence and connection cleanup, URL parsing, quality filtering and command arguments. Tests import the installed wheel in Python isolated mode and check that its declared requirements match requirements.txt, so a dependency edit cannot silently be replaced by an older setup.py pin. No real account, external service or music download is used. All matrix jobs, pip check and named runtime steps must pass before the trusted gate considers merging.

For a signed agent-owned update, the administrator review also binds `author` to the PR login and the PR must use a `dependency-review/` branch. The gate preserves the exact tested signed commit through a guarded fast-forward. Source migrations remain separate commits with their own tests.

When the account publishing a signed agent PR differs from the commit identity, the exact administrator review may also bind `commitAuthor` to the GitHub login shared by the verified commit author and committer. The publishing account remains bound by `author`. This does not relax signatures, same-repository branches, exact head/base, application CI, or the guarded fast-forward. Bot authorship checks remain unchanged.
