import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import flowchart


# Exercise the editor's data and detection without starting a desktop window.
tree = ast.parse((ROOT / "flowchart_studio.py").read_text(encoding="utf8"))
defaults = next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "DEFAULT_SPECS"
                        for t in n.targets))
detect_node = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "_detect_kind")
namespace = {}
exec(compile(ast.Module(body=[detect_node], type_ignores=[]), "studio", "exec"), namespace)


class FishboneTests(unittest.TestCase):
    def render_with_layout_checks(self, spec, output):
        savefig = Figure.savefig

        def inspect_and_save(fig, *args, **kwargs):
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            ax = fig.axes[0]
            boxes = [(text.get_text(), text.get_window_extent(renderer))
                     for text in ax.texts]
            for index, (label, box) in enumerate(boxes):
                self.assertTrue(fig.bbox.contains(box.x0, box.y0), label)
                self.assertTrue(fig.bbox.contains(box.x1, box.y1), label)
                for other_label, other in boxes[index + 1:]:
                    self.assertFalse(box.overlaps(other), (label, other_label))
                for line in ax.lines:
                    path = line.get_path().transformed(line.get_transform())
                    self.assertFalse(path.intersects_bbox(box, filled=False),
                                     f"Line crosses {label!r}")
            savefig(fig, *args, **kwargs)

        with mock.patch.object(Figure, "savefig", inspect_and_save):
            flowchart.render_fishbone(spec, output)

    def test_nested_layout_clearance(self):
        subtree = {"label": "A parent with a long wrapped explanation " * 3,
                   "causes": ["First sub-cause", {
                       "label": "Another intermediate cause",
                       "causes": ["Detailed underlying cause " * 4, "Other cause"]
                   }, "Final sub-cause"]}
        specs = [json.loads(defaults["fishbone"]), {
            "title": "Nested branches above and below",
            "effect": "A long effect description " * 3,
            "categories": [{"label": f"Category {i}",
                            "causes": [subtree, "A sibling cause"]}
                           for i in range(4)]
        }]
        with tempfile.TemporaryDirectory() as directory:
            for spec in specs:
                self.render_with_layout_checks(spec, Path(directory) / "nested.png")

    def test_all_default_kinds_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            for kind, raw in defaults.items():
                with self.subTest(kind=kind):
                    self.assertEqual(namespace["_detect_kind"](json.loads(raw)), kind)
                    source = Path(directory) / f"{kind}.json"
                    output = Path(directory) / f"{kind}.png"
                    source.write_text(raw, encoding="utf8")
                    subprocess.run([sys.executable, str(ROOT / "flowchart.py"),
                                    kind, str(source), str(output)], check=True,
                                   capture_output=True)
                    with Image.open(output) as image:
                        self.assertGreater(image.width, 100)
                        self.assertGreater(image.height, 100)
                        self.assertIsNotNone(image.convert("RGB").getbbox())

    def test_layout_edge_cases(self):
        specs = [
            {"effect": "Problem", "categories": [{"label": "People"}]},
            {"effect": "A long effect " * 12,
             "title": "A long title " * 20,
             "categories": [{"label": "Long category " * 5,
                             "causes": ["A detailed cause " * 10] * 5}
                            for _ in range(5)]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            for spec in specs:
                output = Path(directory) / "diagram.png"
                self.assertEqual(flowchart.render_fishbone(spec, output), output)
                self.assertTrue(output.is_file())
        self.assertEqual(plt.get_fignums(), [])

    def test_more_than_ten_main_branches_and_causes(self):
        spec = {
            "effect": "Problem",
            "categories": [
                {"label": f"Branch {branch}",
                 "causes": [f"Cause {branch}.{cause}" for cause in range(12)]}
                for branch in range(12)
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "large-fishbone.png"
            flowchart.render_fishbone(spec, output)
            with Image.open(output) as image:
                self.assertGreater(image.width, 1000)
                self.assertGreater(image.height, 1000)
        self.assertEqual(plt.get_fignums(), [])

    def test_ten_nested_cause_levels(self):
        cause = "Level 10"
        for level in range(9, 0, -1):
            cause = {"label": f"Level {level}", "causes": [cause]}
        spec = {"effect": "Problem",
                "categories": [{"label": "People", "causes": [cause]}]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested-fishbone.png"
            self.render_with_layout_checks(spec, output)
            with Image.open(output) as image:
                self.assertGreater(image.width, 1000)
                self.assertGreater(image.height, 100)
        self.assertEqual(plt.get_fignums(), [])

    def test_invalid_specs(self):
        for spec in [None, {}, {"effect": " ", "categories": []},
                     {"effect": "Problem", "categories": []},
                     *({"effect": "Problem", "categories": [category]}
                       for category in [None, {}, {"label": ""},
                                        {"label": "People", "causes": "cause"},
                                        {"label": "People", "causes": [5]},
                                        {"label": "People", "causes": [
                                            {"label": "Child", "causes": "bad"}]},
                                        {"label": "People", "style": "missing"}])]:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                flowchart.render_fishbone(spec, "unused.png")
        self.assertEqual(plt.get_fignums(), [])


if __name__ == "__main__":
    unittest.main()
