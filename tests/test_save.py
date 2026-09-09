import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import flowchart_studio


class _Editor:
    def __init__(self, text):
        self.text = text

    def get(self, _start, _end):
        return self.text


class SaveTests(unittest.TestCase):
    def studio(self, path, text="updated"):
        studio = flowchart_studio.FlowchartStudio.__new__(
            flowchart_studio.FlowchartStudio)
        studio._path = path
        studio._disk_mtime = None
        studio.editor = _Editor(text)
        studio.status = SimpleNamespace(set=mock.Mock())
        studio._mark_clean = mock.Mock()
        studio._set_title = mock.Mock()
        return studio

    def test_save_open_file_without_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "opened.json"
            path.write_text("old", encoding="utf8")
            studio = self.studio(str(path))
            with mock.patch.object(flowchart_studio.filedialog,
                                   "asksaveasfilename") as dialog:
                studio.save_spec()
            dialog.assert_not_called()
            self.assertEqual(path.read_text(encoding="utf8"), "updated")
            self.assertEqual(studio._path, str(path))

    def test_save_new_file_asks_once_and_adopts_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.json"
            studio = self.studio(None)
            with mock.patch.object(flowchart_studio.filedialog,
                                   "asksaveasfilename", return_value=str(path)):
                studio.save_spec()
            self.assertEqual(path.read_text(encoding="utf8"), "updated")
            self.assertEqual(studio._path, str(path))

    def test_save_as_always_asks_for_new_path(self):
        with tempfile.TemporaryDirectory() as directory:
            old_path = Path(directory) / "old.json"
            new_path = Path(directory) / "new.json"
            old_path.write_text("original", encoding="utf8")
            studio = self.studio(str(old_path))
            with mock.patch.object(flowchart_studio.filedialog,
                                   "asksaveasfilename",
                                   return_value=str(new_path)) as dialog:
                studio.save_spec_as()
            dialog.assert_called_once()
            self.assertEqual(old_path.read_text(encoding="utf8"), "original")
            self.assertEqual(new_path.read_text(encoding="utf8"), "updated")
            self.assertEqual(studio._path, str(new_path))


if __name__ == "__main__":
    unittest.main()
