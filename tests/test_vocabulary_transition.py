"""aegis-v2o: a fresh CLI export emits no old-namespace IRI, and a record
stored under the former-name (legacy) terms still verifies.

The signed bytes are `shuttle-transition-v1|run_iri|step|from|to|at|agent`;
no vocabulary IRI is inside them, so moving predicates to the published
w3id terms cannot invalidate an existing signature.
"""
import unittest
import json
from unittest import mock

from shuttle import cli, quipu_client as qc, signing, state, vocabulary
from tests import test_export_and_cli as base

OLD = ('aegis.gastown.local', 'scbrown.github.io/quechua')


class VocabularyTransition(base.EnvIsolatedCase):
    _define = base.CliFlowTests._define

    def _flow(self):
        self.run_cli("define", self._define())
        self.run_cli("start", "triage", "r1", "--agent", "agent-a",
                     "--at", "2026-08-01T00:00:00Z")
        self.run_cli("advance", "r1", "--step", "claim", "--agent", "agent-a")
        self.run_cli("advance", "r1", "--step", "finish", "--agent", "agent-a")

    def test_fresh_export_and_registration_emit_zero_old_namespace_iris(self):
        self._flow()
        with mock.patch.object(qc, "probe_graph_kinds", return_value=[]):
            self.assertEqual(0, self.run_cli("export")[0])
        _, registration = self.run_cli("keys", "init", "agent-a", "--workflow", "triage")
        bodies = [b.get("turtle", "") for p, b in self.posts if p == "/knot"]
        self.assertEqual(5, len(bodies))
        for body in [*bodies, registration]:
            for old in OLD:
                self.assertNotIn(old, body)
        self.assertTrue(any(vocabulary.CORE + "signature" in b or "core:signature" in b
                            for b in bodies))

    def test_signed_bytes_carry_no_vocabulary_namespace(self):
        msg = signing.transition_message("urn:shuttle:run:r1", "claim", "open",
                                         "claimed", "2026-08-01T00:00:00Z", "agent-a")
        for ns in (vocabulary.LEGACY, vocabulary.CORE, vocabulary.QUIPU):
            self.assertNotIn(ns.encode(), msg)

    def test_a_record_stored_under_legacy_terms_still_verifies(self):
        self._flow()
        claim = next(r for r in state.records() if r.get("step") == "claim")
        run_iri = "urn:shuttle:run:r1"
        # Rows as quipu returns them for a historical record written with the
        # former-name predicates; the event subject is instance identity and
        # is kept byte-for-byte.
        event_rows = [{"ev": vocabulary.LEGACY + "event/r1/3",
                       "step": "urn:shuttle:workflow:triage/step/claim",
                       "from": claim["from"], "to": claim["to"], "at": claim["at"],
                       "agent": "urn:shuttle:agent:agent-a", "sig": claim["signature"]}]
        reg_rows = [{"verifier": "agent-a", "pk": signing.public_key_hex("agent-a")}]
        queries = []

        start = next(r for r in state.records() if r['type'] == 'start')

        def fake_query(sparql, graph=None, **kwargs):
            queries.append(sparql)
            if 'SELECT DISTINCT ?at' in sparql:
                return {'rows': [{'at': start['at']}]}
            if 'SELECT ?record' in sparql:
                return {'rows': [{'record': json.dumps(start)}]}
            return {"rows": reg_rows if '?verifier ?pk' in sparql else event_rows}

        with mock.patch.object(qc, "query", side_effect=fake_query):
            code, out = self.run_cli("verify", "r1")
        self.assertEqual(0, code, out)
        self.assertIn("all 1 exported transitions verify", out)
        for name in ("inRun", "signature", "performedBy"):
            self.assertIn("<" + vocabulary.LEGACY + name + ">", queries[2])
            self.assertIn("<" + vocabulary.term(name) + ">", queries[2])
        self.assertIn("<" + vocabulary.LEGACY + "VerifierRegistration>", queries[3])
        self.assertIn(run_iri, queries[2])
        # Control: the same legacy row with a tampered signature is refused.
        event_rows[0]["sig"] = ("00" if claim["signature"][:2] != "00" else "11") + claim["signature"][2:]
        queries.clear()
        with mock.patch.object(qc, "query", side_effect=fake_query):
            code, out = self.run_cli("verify", "r1")
        self.assertEqual(1, code, out)
        self.assertIn("BAD SIGNATURE", out)


if __name__ == "__main__":
    unittest.main()
