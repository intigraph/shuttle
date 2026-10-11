# Release PR authentication

This stages the credential split already prepared in Yupana PR86.
Do not merge the producer until the required repository secret exists.
Missing-secret preflight fails before any release action; there is no
GITHUB_TOKEN fallback. Repository settings are not changed by this source.

| Operation | Credential |
|---|---|
| Create or refresh the version/changelog release PR | RELEASE_PLZ_TOKEN |
| Create the tag and draft release after its reviewed merge | GITHUB_TOKEN |
| Validate, upload immutable assets and publish in the same run | GITHUB_TOKEN |

The non-workflow identity lets the generated PR receive normal CI. The workflow
token's tag must not be assumed to trigger a second workflow: the producer calls
the existing guarded publisher in the same run. Keep the outside-fork approval
policy and complete-green merge gates. A passing source test is not generated-PR
or release acceptance. Never publish an existing public release or clobber assets.

## Exact provisioning step

Repository owner: create a fine-grained PAT scoped only to scbrown/shuttle,
with Contents read/write and Pull requests read/write, using the same existing
Yupana/Quipu release-PR identity route. Set it as the Actions repository secret
RELEASE_PLZ_TOKEN. Use an explicit expiration and record the renewal owner/date
in the private operational trail. Do not put a token in this repository, an issue,
a command argument or a log. No Actions-admin or workflow-setting change is
requested. Crew stages the wiring; the owner supplies the secret through the
normal secret UI.

## Acceptance

After provisioning, exact-head review and complete source/base CI must pass.
Observe a real producer push creating/updating its version PR, complete required
CI on that exact generated head, its normal reviewed merge, and successful
same-run version-matched asset publication. Then verify the scheduled release
mode checker reports release-pr. No hand tag, synthetic release or unchecked
manual dispatch is an acceptance substitute. Roll back source through reviewed
revert; never delete or rewrite a published release/tag.
