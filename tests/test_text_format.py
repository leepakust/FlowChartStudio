import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from matplotlib.figure import Figure

import flowchart
from text_format import COLORS, format_at_cursor, format_whole_chart
from test_fishbone import defaults


class TextFormattingTests(unittest.TestCase):
    def edit(self, source, cursor, options):
        start, end, replacement = format_at_cursor(source, cursor, options)
        return source[:start] + replacement + source[end:]

    def test_preserves_source_and_updates_existing_options(self):
        source = '{\n  "nodes": [{"id":"a", "text":"Hello"}]\n}\n'
        result = self.edit(source, source.index("Hello"), {"bold": True})
        self.assertEqual(result, source.replace('"Hello"', '{"text": "Hello", "bold": true}'))
        result = self.edit(result, result.index("Hello"), {"italic": True})
        label = json.loads(result)["nodes"][0]["text"]
        self.assertTrue(label["bold"])
        self.assertTrue(label["italic"])
        result = self.edit(result, result.index("Hello"), {"bold": False})
        self.assertFalse(json.loads(result)["nodes"][0]["text"]["bold"])

    def test_targets_causes_edges_and_nearest_label(self):
        for source, text in [
            ('{"categories":[{"label":"People","causes":["Training"]}]}', "Training"),
            ('{"edges":[["a","b","Next"]]}', "Next"),
            ('{"title":"Overview","effect":"Delay"}', "Delay"),
        ]:
            result = self.edit(source, source.index(text), {"color": COLORS["Red"]})
            self.assertIn('"color": "#FF0000"', result)
            json.loads(result)
        with self.assertRaises(ValueError):
            self.edit('{"nodes":[{"id":"only-id"}]}', 20, {"bold": True})

    def test_whole_chart_and_invalid_input(self):
        source = '{"nodes": []}\n'
        for options in ({"font_size": 12}, {"bold": True}):
            start, end, replacement = format_whole_chart(source, options)
            source = source[:start] + replacement + source[end:]
        self.assertEqual(json.loads(source)["text_format"], {"font_size": 12, "bold": True})
        for options in ({"font_size": -1}, {"font_size": float("nan")},
                        {"bold": "true"}, {"color": "invalid"}):
            with self.assertRaises(ValueError):
                format_at_cursor('{"title":"Test"}', 12, options)
        with self.assertRaises(ValueError):
            format_at_cursor('{"title":', 8, {"bold": True})

    def test_render_formatting_in_every_chart(self):
        options = {"font_size": 16, "bold": True, "italic": True,
                   "underline": True, "color": COLORS["Purple"]}
        renderers = {"flow": flowchart.render, "timeline": flowchart.render_timeline,
                     "sequence": flowchart.render_sequence, "fishbone": flowchart.render_fishbone}
        savefig = Figure.savefig
        for kind, render in renderers.items():
            spec = json.loads(defaults[kind])
            spec["text_format"] = options
            original = copy.deepcopy(spec)
            captured = []

            def inspect(fig, *args, **kwargs):
                fig.canvas.draw()
                if kind == "sequence":
                    ax = fig.axes[0]
                    for patch in ax.patches:
                        if isinstance(patch, flowchart.FancyBboxPatch):
                            bounds = patch.get_window_extent()
                            self.assertGreaterEqual(bounds.x0, ax.bbox.x0)
                            self.assertLessEqual(bounds.x1, ax.bbox.x1)
                for text in fig.axes[0].texts:
                    if not text.get_text():
                        continue  # Arrow annotations contain no display text.
                    self.assertEqual(text.get_fontsize(), 16)
                    self.assertEqual(text.get_fontweight(), "bold")
                    self.assertEqual(text.get_fontstyle(), "italic")
                    self.assertEqual(text.get_color(), COLORS["Purple"])
                    self.assertTrue(text.underline)
                    captured.append(text.get_text())
                savefig(fig, *args, **kwargs)

            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                with mock.patch.object(Figure, "savefig", inspect):
                    render(spec, Path(directory) / "formatted.png")
                self.assertTrue(captured)
                self.assertEqual(spec, original)

    def test_local_style_overrides_defaults_and_wrapping(self):
        spec = {"text_format": {"bold": True, "font_size": 10},
                "effect": "Delay", "categories": [{"label": "People", "causes": [
                    {"text": "A very long training cause " * 4, "bold": False,
                     "font_size": 18, "color": COLORS["Blue"]}]}]}
        savefig = Figure.savefig

        def inspect(fig, *args, **kwargs):
            label = next(t for t in fig.axes[0].texts if "training" in t.get_text())
            self.assertIn("\n", label.get_text())
            self.assertEqual(label.get_fontsize(), 18)
            self.assertEqual(label.get_fontweight(), "normal")
            self.assertEqual(label.get_color(), COLORS["Blue"])
            savefig(fig, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(Figure, "savefig", inspect):
                flowchart.render_fishbone(spec, Path(directory) / "local.png")

    def test_local_formatting_in_flow_timeline_and_sequence(self):
        specs = {kind: json.loads(defaults[kind]) for kind in ("flow", "timeline", "sequence")}
        rich = {"text": "Styled label", "font_size": 18, "bold": False,
                "italic": True, "underline": True, "color": COLORS["Teal"]}
        specs["flow"]["nodes"][0]["text"] = rich
        specs["flow"]["edges"][0].append(rich)
        specs["timeline"]["title"] = rich
        specs["timeline"]["lanes"][0]["label"] = rich
        specs["timeline"]["bars"][0]["label"] = rich
        specs["timeline"]["events"][0]["label"] = rich
        specs["sequence"]["actors"][0]["label"] = rich
        specs["sequence"]["messages"][0]["label"] = rich
        specs["sequence"]["messages"][-1]["note"] = rich
        savefig = Figure.savefig
        renderers = {"flow": flowchart.render, "timeline": flowchart.render_timeline,
                     "sequence": flowchart.render_sequence}
        for kind, spec in specs.items():
            found = []

            def inspect(fig, *args, **kwargs):
                fig.canvas.draw()
                for artist in fig.axes[0].texts:
                    if artist.get_text() == "Styled label":
                        self.assertEqual(artist.get_fontsize(), 18)
                        self.assertEqual(artist.get_fontweight(), "normal")
                        self.assertEqual(artist.get_fontstyle(), "italic")
                        self.assertEqual(artist.get_color(), COLORS["Teal"])
                        self.assertTrue(artist.underline)
                        found.append(artist)
                savefig(fig, *args, **kwargs)

            with tempfile.TemporaryDirectory() as directory:
                with mock.patch.object(Figure, "savefig", inspect):
                    renderers[kind](spec, Path(directory) / "local.png")
            self.assertEqual(len(found), {"flow": 2, "timeline": 4, "sequence": 3}[kind])
