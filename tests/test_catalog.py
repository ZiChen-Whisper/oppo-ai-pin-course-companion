import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from store import Store, atomic_json
from catalog import catalog, update_materials


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.course = self.store.save_course({'name': '课程', 'root': self.temp.name}, 0)
        self.path = str(Path(self.temp.name) / '作业' / '作业要求.md')
        self.other = str(Path(self.temp.name) / '课件.pptx')
        atomic_json(self.store.root / 'indexes' / (self.course['id'] + '.json'), {
            'indexed_at': '2026-10-19T00:00:00Z', 'files': [
                {'path': self.path, 'type': 'lab'}, {'path': self.other, 'type': 'slides'}]})

    def test_usage_and_format_are_separate_and_suggestions_unconfirmed(self):
        item = catalog(self.store, self.course['id'])['files'][0]
        self.assertEqual((item['type'], item['format'], item['confirmed']), ('assignment-brief', 'MD', False))

    def test_manual_overrides_persist_and_survive_index_replacement(self):
        update_materials(self.store, {'course_id': self.course['id'], 'revision': 1,
            'paths': [self.path], 'type': 'reference', 'notes': '保留备注'})
        atomic_json(self.store.root / 'indexes' / (self.course['id'] + '.json'), {'files': [{'path': self.path, 'type': 'lab'}]})
        item = catalog(Store(self.temp.name), self.course['id'])['files'][0]
        self.assertEqual((item['type'], item['source'], item['confirmed'], item['notes']), ('reference', 'manual', True, '保留备注'))

    def test_batch_is_atomic_on_invalid_path_and_stale_revision(self):
        for changes in [{'paths': [self.path, '/outside']}, {'paths': [self.path], 'revision': 0}]:
            with self.assertRaises(ValueError):
                update_materials(self.store, {'course_id': self.course['id'], 'revision': 1, **changes})
            self.assertEqual(self.store.registry()['revision'], 1)
            self.assertEqual(self.store.course(self.course['id'])['materials'], [])

    def test_changing_primary_preserves_other_overrides(self):
        update_materials(self.store, {'course_id': self.course['id'], 'revision': 1, 'paths': [self.path], 'primary': True})
        update_materials(self.store, {'course_id': self.course['id'], 'revision': 2, 'paths': [self.other], 'primary': True})
        items = self.store.course(self.course['id'])['materials']
        self.assertEqual([m['path'] for m in items if m.get('primary')], [self.other])
        self.assertTrue(next(m for m in items if m['path'] == self.path)['confirmed'])

    def test_old_manual_material_is_preserved(self):
        self.store.save_course({**self.course, 'materials': [{'path': self.path, 'type': 'textbook-markdown', 'notes': '教材'}]}, 1)
        item = catalog(self.store, self.course['id'])['files'][0]
        self.assertEqual(item['type'], 'textbook')
        self.assertTrue(item['confirmed'])


if __name__ == '__main__':
    unittest.main()
