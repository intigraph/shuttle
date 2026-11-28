# Complete exported records

Each exported definition carries its full JSON record as an RDF `rdf:value`
literal, including initial and terminal states, transition edges, seed settings
and any supplied evidence. Transition events carry their complete records too,
so evidence survives export. JSON escaping preserves quotes and newlines.
These literals supplement the existing workflow and transition facts.

New CLI, imported and scheduled run starts carry an ed25519 signature over
`shuttle-start-v1|` followed by compact, ASCII JSON of
`[run_iri, definition_name, initial_state, at, agent]`. This is a separate
message domain. Existing `shuttle-transition-v1` signed bytes do not change.
Definition content and evidence remain unsigned; step-record digest signing
belongs to a later protocol.

`shuttle verify RUN` discovers the creation time across Quipu's operational
and archive graphs, then reads the run window and registered identity keys.
It never reads local state or signing keys. It verifies the signed start and
each exported transition; incomplete records and truncated queries refuse.
It does not prove transition sequence legality or signer authorization.
Historical starts without the new signed record cannot pass verification.
Export refuses unsigned starts rather than inventing an attestation for them;
retain the original history for an explicit migration decision.

`shuttle define` refuses an existing name under the state lock. Use a new
name for a revised workflow.

The standalone installer publishes both `shuttle` and `shuttle-signer` after
checking the wheel and entrypoints. Release acceptance additionally requires
publishing the release artifact and reading both commands back from a clean
install; installer fixtures alone do not establish publication.
