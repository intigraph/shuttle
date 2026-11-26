"""aegis-3r1: every old-namespace use in the repository-share/knowledge tooling
is classified and labelled, and the knowledge build emits no unlabelled
old-namespace vocabulary.

Classification (old namespace http://aegis.gastown.local/ontology/):
  alias              - an already-published pendant/share entity name that the
                       release query renames to https://w3id.org/intigraph/<repo>/id/
                       and links back with owl:sameAs. Kept so readers resolve.
  unowned-vocabulary - the stack-wide repository-pendant predicates/classes that
                       Bobbin emits and the shipped share shapes validate. No
                       w3id owner is published for them (shuttle/vocabulary.py
                       owns workflow terms only), so moving them here alone
                       would leave the producer read and the shapes disjoint.
A new, unclassified use changes a pinned count below and fails this test.
"""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OLD = re.compile(r'aegis(\.|\[\.\])gastown(\.|\[\.\])local')
MARKER = 'former-namespace (aegis-3r1)'
# file -> number of lines naming the old namespace (all classified in-file).
CLASSIFIED = {
    'queries/repository-share-shuttle.rq': 14,   # 1 vocabulary prefix, 13 alias
    'scripts/build-repository-knowledge.py': 1,  # alias subjects + vocabulary
    'scripts/build-repository-share.py': 2,      # 1 alias, 1 vocabulary
    'scripts/publish_repository_share.py': 1,    # vocabulary
    'scripts/test-repository-share-query.py': 1,         # fixture
    'scripts/test-repository-share-publication.py': 1,   # fixture
}
A = 'http://aegis.gastown.local/ontology/'
ALIAS_SUBJECTS = (A + 'doc/shuttle/', A + 'code/shuttle/')
# Entity names the release query renames (and sameAs-links) in object position.
ALIAS_OBJECT = re.compile(
    re.escape(A) + r'((code|doc|chunk)/[^/]+/.+|repo_[A-Za-z0-9-]+'
    r'|repo-embedded-knowledge-databases-directive-2026-09-03)$')
IRI = re.compile(r'<([^>]*)>')


def load_knowledge():
    spec = importlib.util.spec_from_file_location(
        'build_repository_knowledge', ROOT / 'scripts/build-repository-knowledge.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def released_predicates():
    query = (ROOT / 'queries/repository-share-shuttle.rq').read_text()
    return {A + name for name in re.findall(r'\baegis:(\w+)', query)}


class Classification(unittest.TestCase):
    def test_every_old_namespace_use_is_pinned_and_labelled(self):
        for path, count in CLASSIFIED.items():
            text = (ROOT / path).read_text()
            with self.subTest(path=path):
                lines = [line for line in text.splitlines() if OLD.search(line)]
                self.assertEqual(len(lines), count, 'reclassify: ' + path)
                self.assertIn(MARKER, text)
                for label in text.split(MARKER)[1:]:
                    self.assertRegex(label[:600], r'alias|unowned-vocabulary|fixture')

    def test_knowledge_build_emits_only_alias_subjects_and_released_vocabulary(self):
        module = load_knowledge()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry = json.loads((ROOT / 'docs/knowledge/repository-knowledge.json').read_text())
            for source in {r['source'] for r in registry['records']}:
                (root / source).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / source, root / source)
            (root / 'docs/knowledge').mkdir(parents=True, exist_ok=True)
            (root / 'docs/knowledge/repository-knowledge.json').write_text(json.dumps(registry))
            text = module.render(root, '1' * 40, lambda _: 'fixture label')
        vocabulary = released_predicates() | {A + 'Concept', A + 'DecisionRecord'}
        seen_alias = seen_vocabulary = 0
        for line in text.splitlines():
            iris = IRI.findall(line)
            subject, predicate, rest = iris[0], iris[1], iris[2:]
            if subject.startswith(A):
                self.assertTrue(subject.startswith(ALIAS_SUBJECTS), line)
                seen_alias += 1
            if predicate.startswith(A):
                self.assertIn(predicate, vocabulary, 'unlabelled vocabulary: ' + line)
                seen_vocabulary += 1
            for obj in rest:
                if obj.startswith(A) and not ALIAS_OBJECT.match(obj):
                    self.assertIn(obj, vocabulary, 'unlabelled object: ' + line)
        self.assertGreater(seen_alias, 0)
        self.assertGreater(seen_vocabulary, 0)


if __name__ == '__main__':
    unittest.main()
