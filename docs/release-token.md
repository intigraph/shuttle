# Release PR auth route

This copies the route currently running in Bobbin and Yupana: GITHUB_TOKEN
creates the release PR and the existing operator-side scoped approval job
unparks its bot-authored required CI. No new token or secret is required.
The future RELEASE_PLZ_TOKEN template in Yupana PR86 is not the live route
and is not activated here.

## Paired activation, never a settings flag alone

Keep this producer PR draft until exact-head source review and completeCI pass,
and the existing approve-parked-release-runs.sh has reviewed enrolment for
scbrown/shuttle installed from its normal neutral execution copy. Then enable
the repository's Allow Actions to create and approve pull requests setting
as the paired approved action, leaving outside-fork contributor policy intact.
Do not widen the approver beyond the exact repo, bot-authored release branch,
open PR, newest workflow run and no active same-workflow guard.

Publication retains the workflow token and same-run guarded publisher: do not
assume the created tag triggers another workflow. The real acceptance is a
generated release PR whose parked runs are approved by the existing scheduled
path, complete exact-head CI, normal reviewed merge, then version-matched
publication and a scheduled release-mode transition. SourceCI is not acceptance.
No hand tag, synthetic release, secret copy or global fork-policy relaxation.

Rollback uses reviewed source revert and restores the pre-change repo setting
under the same approved plan; never rewrite a published tag or release.
