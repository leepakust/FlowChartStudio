import copy
import json
import os
import tempfile
import unittest

import flowchart


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")


class RendererSmokeTests(unittest.TestCase):
    def _load(self, name):
        with open(os.path.join(EXAMPLES, name), encoding="utf8") as f:
            return json.load(f)

    def _render(self, fn, spec, ext="png"):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, f"out.{ext}")
            fn(spec, path)
            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 100)

    def test_all_renderers_png(self):
        self._render(flowchart.render, self._load("flow_auto.json"))
        self._render(flowchart.render, self._load("state_machine.json"))
        self._render(flowchart.render_timeline, self._load("timeline.json"))
        self._render(flowchart.render_sequence, self._load("sequence.json"))
        self._render(flowchart.render_tasks, self._load("tasks.json"))

    def test_vector_export(self):
        self._render(flowchart.render, self._load("flow_auto.json"), "svg")
        self._render(flowchart.render_tasks, self._load("tasks.json"), "pdf")

    def test_render_does_not_mutate_input(self):
        spec = self._load("flow_auto.json")
        before = copy.deepcopy(spec)
        self._render(flowchart.render, spec)
        self.assertEqual(spec, before)

    def test_validation_collects_actionable_errors(self):
        bad = {
            "nodes": [{"id": "A", "text": "x", "shape": "unknown"}],
            "edges": [["A", "missing"]]
        }
        with self.assertRaises(flowchart.SpecValidationError) as ctx:
            flowchart.validate_spec(bad, "flow")
        text = str(ctx.exception)
        self.assertIn("unknown", text)
        self.assertIn("missing", text)


if __name__ == "__main__":
    unittest.main()
