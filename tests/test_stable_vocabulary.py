"""Fresh exports use published terms; historical signed identities stay intact."""
import unittest
from unittest import mock
import json
from pathlib import Path

from shuttle import export, signing

LEGACY = 'http://aegis.gastown.local/ontology/'
CORE = 'https://w3id.org/intigraph/camayoc/core/ns#'
QUIPU = 'https://w3id.org/intigraph/quipu/ns#'


class StableVocabulary(unittest.TestCase):
    def test_every_writer_term_matches_the_retained_published_crosswalk(self):
        from shuttle import vocabulary as vocab
        snapshot = json.loads((Path(__file__).parent / 'fixtures/shuttle-ownership.json').read_text())
        self.assertEqual(len(snapshot['terms']), 19)
        self.assertEqual(set(vocab._ALIASES), {row['old'] for row in snapshot['terms']})
        for row in snapshot['terms']:
            self.assertEqual(vocab.term(row['old'][len(LEGACY):]), row['new'])

    def test_fresh_definition_start_transition_and_registration_have_no_old_terms(self):
        definition = {'name': 'example', 'transitions': [{'step': 'claim'}]}
        record = {'run': 'r1', 'definition': 'example', 'state': 'open',
                  'at': '2026-11-13T00:00:00Z', 'agent': 'fixture',
                  'step': 'claim', 'from': 'open', 'to': 'claimed', 'signature': 'ab' * 64}
        with mock.patch.dict('os.environ', {'SHUTTLE_ENTITY_NS': 'urn:shuttle:'}), \
                mock.patch.object(signing, 'public_key_hex', return_value='cd' * 32):
            bodies = [export.definition_turtle(definition), export.start_turtle(record),
                      export.transition_turtle(record, 3),
                      signing.registration_turtle('fixture', 'urn:shuttle:workflow:example')]
        for body in bodies:
            with self.subTest(body=body):
                self.assertNotIn(LEGACY, body)
                self.assertNotIn('scbrown.github.io/quechua', body)
                self.assertIn(QUIPU, body)
                self.assertIn(CORE, body)
        self.assertIn('urn:shuttle:run:r1', bodies[1])

    def test_mapped_terms_and_legacy_query_paths_are_exact(self):
        from shuttle import vocabulary as vocab
        self.assertEqual(vocab.term('WorkflowRun'), QUIPU + 'WorkflowRun')
        self.assertEqual(vocab.term('currentState'), CORE + 'currentState')
        self.assertIn('<' + LEGACY + 'inRun>', vocab.path('inRun'))
        self.assertIn('<' + CORE + 'inRun>', vocab.path('inRun'))
        with self.assertRaises(KeyError):
            vocab.term('InventedTerm')

    def test_normalization_keeps_instance_identity_and_detectable_alias_duplicates(self):
        from shuttle import vocabulary as vocab
        subject = LEGACY + 'historical-run'
        old = {'ev': subject, 'p': LEGACY + 'inRun', 'value': subject, 'iri': True}
        new = {**old, 'p': CORE + 'inRun'}
        rows = [vocab.normalize_fact(row) for row in [old, new]]
        self.assertEqual(rows, [new, new])
        self.assertEqual(len(rows), 2)  # strict consumers must still see the collision
        self.assertEqual(old['p'], LEGACY + 'inRun')  # source is not mutated


if __name__ == '__main__':
    unittest.main()
