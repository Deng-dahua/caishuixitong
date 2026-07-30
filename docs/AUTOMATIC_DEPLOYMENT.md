# Automatic deployment channel

The local production instance is updated through a current-user deployment
broker. The broker accepts only a complete committed Git diff from the
designated source repository and applies it to the fixed application runtime.

Every deployment performs these controls:

1. Verify the repository HEAD, clean working tree, complete diff, safe relative
   paths, and SHA-256 hashes.
2. Reject runtime data, databases, environment files, private keys, virtual
   environments, Git metadata, and paths outside the approved roots.
3. Run release checks and the complete regression suite before stopping the
   service.
4. Create a rollback backup, apply files atomically, and repeat release checks
   and regression tests against the runtime.
5. Restart the service and require a successful health check.
6. Restore the previous files and restart the previous version automatically
   if any post-stop step fails.

The broker runs under the current Windows user, starts at logon, and is kept
alive by a single-instance watchdog. Deployment requests and results are
auditable in the workspace deployment channel; application secrets and
business data never enter that channel.
