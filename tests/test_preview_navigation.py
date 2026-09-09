"""Exercise preview coordinates and image cropping without a desktop window."""
from types import SimpleNamespace
import unittest
from unittest import mock

from PIL import Image
from flowchart_studio import FlowchartStudio


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Canvas:
    def __init__(self):
        self.x, self.y = 0.0, 0.0
        self.region = (0, 0, 1000, 600)
        self.items = {}

    def winfo_width(self):
        return 500

    def winfo_height(self):
        return 300

    def canvasx(self, x):
        return self.x + x

    def canvasy(self, y):
        return self.y + y

    def configure(self, **options):
        self.region = options.get("scrollregion", self.region)

    def xview_moveto(self, fraction):
        self.x = self.region[0] + fraction * (self.region[2] - self.region[0])

    def yview_moveto(self, fraction):
        self.y = self.region[1] + fraction * (self.region[3] - self.region[1])

    def create_image(self, x, y, **options):
        self.items[1] = {"x": x, "y": y, **options}
        return 1

    def coords(self, item, x, y):
        self.items[item].update(x=x, y=y)

    def itemconfigure(self, item, **options):
        self.items[item].update(options)


class PreviewTests(unittest.TestCase):
    def studio(self):
        studio = FlowchartStudio.__new__(FlowchartStudio)
        studio._current_image = Image.new("RGB", (1000, 600), "white")
        studio._preview_scale = None
        studio._preview_draw_id = None
        studio._canvas_image_id = None
        studio._zoom = Value("100%")
        studio.preview_canvas = Canvas()
        studio._queue_preview_draw = mock.Mock()
        return studio

    def test_zoom_keeps_pointer_on_same_image_point(self):
        studio = self.studio()
        studio._refresh_preview()
        canvas = studio.preview_canvas
        x, y = 83, 127
        before = (canvas.canvasx(x), canvas.canvasy(y))
        studio._zoom_preview_wheel(SimpleNamespace(delta=120, x=x, y=y))
        self.assertAlmostEqual(canvas.canvasx(x) / studio._preview_scale, before[0])
        self.assertAlmostEqual(canvas.canvasy(y) / studio._preview_scale, before[1])
        studio._zoom_preview_wheel(SimpleNamespace(delta=-120, x=x, y=y))
        self.assertAlmostEqual(studio._preview_scale, 1.0, places=5)
        self.assertAlmostEqual(canvas.canvasx(x), before[0], places=4)

    def test_fit_centers_and_wheel_limits(self):
        studio = self.studio()
        studio._zoom.set("Fit")
        studio._refresh_preview()
        self.assertEqual(studio._preview_scale, 0.5)
        self.assertAlmostEqual(studio.preview_canvas.canvasx(250), 250)
        self.assertAlmostEqual(studio.preview_canvas.canvasy(150), 150)
        for _ in range(5):
            studio._zoom_preview_wheel(SimpleNamespace(delta=2400, x=200, y=100))
        self.assertEqual(studio._preview_scale, 8.0)
        for _ in range(5):
            studio._zoom_preview_wheel(SimpleNamespace(delta=-2400, x=200, y=100))
        self.assertEqual(studio._preview_scale, 0.01)

    def test_high_zoom_only_allocates_visible_bitmap_and_can_return_from_blank(self):
        studio = self.studio()
        studio._zoom.set("800%")
        studio._refresh_preview()
        with mock.patch("flowchart_studio.ImageTk.PhotoImage", side_effect=lambda img: img):
            studio._draw_preview_viewport()
            self.assertLessEqual(studio._photo.width, 500)
            self.assertLessEqual(studio._photo.height, 300)
            studio.preview_canvas.x = -600
            studio._draw_preview_viewport()
            self.assertEqual(studio.preview_canvas.items[1]["state"], "hidden")
            studio.preview_canvas.x = 0
            studio._draw_preview_viewport()
            self.assertEqual(studio.preview_canvas.items[1]["state"], "normal")
        self.assertEqual(studio._current_image.size, (1000, 600))

    def test_empty_preview_ignores_wheel(self):
        studio = self.studio()
        studio._current_image = None
        self.assertEqual(studio._zoom_preview_wheel(SimpleNamespace(delta=120)), "break")


if __name__ == "__main__":
    unittest.main()
