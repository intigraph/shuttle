# Stable vocabulary and historical run identity

Fresh workflow, start, transition and verifier-registration Turtle uses the
published Intigraph vocabulary. The 19-term crosswalk comes from
[ownership.json](https://intigraph.ai/ids/ownership.json), SHA-256
`a389be53b74259d0c515ff6db16d602474dc5fe38dc6cc47f0f54a2d1347d34e`.
Five classes belong to `https://w3id.org/intigraph/quipu/ns#`; fourteen properties
belong to `https://w3id.org/intigraph/camayoc/core/ns#`.
Unknown term names refuse instead of falling back to another vocabulary.

Vocabulary ownership is separate from instance identity. The existing neutral
`urn:shuttle:` instance default and explicit `SHUTTLE_ENTITY_NS` contract remain.
Run, workflow, step, event and registration identities, signature messages, local
logs and watermarks retain their existing bytes. This change allocates no new
identity scheme, invokes no scoped mint, enrolls no verifier and rewrites no
historical graph. An explicitly configured historical instance base remains an
operator-controlled identity parameter; it must not be changed to migrate terms.

Verification and signed fixed/calendar history readers query both the published
and historical literal predicates using explicit UNION branches, retaining the
established native-reader compatibility form rather than alternate predicate
paths for literal objects. Known vocabulary terms are normalized only
for comparison; subject and reference identities and signatures remain exact.
Duplicate aliases remain visible to existing cardinality checks and refuse.
No inference or `sameAs` activation is required for these readers.

The legacy constant in `vocabulary.py` is a read-compatibility identifier.
Repository-share builders and queries retain their separate former-name contract
and private intermediate-index behavior; their old IRIs are not rewritten by
the runtime workflow writer change.

Source tests prove the fresh default builders emit no old vocabulary IRIs and
historical signed facts remain readable. They do not establish installed,
released or live-store acceptance. Deployment still needs compatible loaded
shapes, normal release/adoption, one smoke check and an explicit rollback.
Source rollback is a normal revert; preserve existing outboxes and identities.
