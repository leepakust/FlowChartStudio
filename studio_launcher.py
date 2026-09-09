"""Windowed executable entry point and packaged-runtime smoke check."""
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


def main():
    # Extended Windows paths avoid Tcl path normalization failures, including
    # long installation paths. PyInstaller sets these before this entry point.
    if os.name == "nt" and getattr(sys, "frozen", False):
        for variable in ("TCL_LIBRARY", "TK_LIBRARY"):
            path = os.environ.get(variable)
            if path and not path.startswith("\\\\?\\"):
                os.environ[variable] = "\\\\?\\" + os.path.abspath(path)
    import flowchart_studio as studio
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        report = Path(sys.argv[2]).resolve()
        app = None
        try:
            app = studio.FlowchartStudio()
            app.withdraw()
            app.update()
            assert studio.HAVE_CLIPBOARD, "Windows clipboard support missing"
            with tempfile.TemporaryDirectory() as folder:
                for kind, (render, _) in studio.RENDERERS.items():
                    for extension in ("png", "svg", "pdf"):
                        target = Path(folder) / f"{kind}.{extension}"
                        render(json.loads(studio.DEFAULT_SPECS[kind]), str(target))
                        assert target.stat().st_size > 100, str(target)
                app.render_now()
                assert app._current_image is not None, app.status.get()
            report.write_text(json.dumps({"ok": True, "frozen": bool(getattr(sys, "frozen", False)),
                                         "checks": ["Tk UI", "live preview", "clipboard import", "four diagram kinds in PNG/SVG/PDF"]}, indent=2))
        except Exception:
            report.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}, indent=2))
            raise
        finally:
            if app is not None:
                app.destroy()
    else:
        app = studio.FlowchartStudio()
        app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if "--self-test" in sys.argv:
            sys.exit(1)
        log_dir = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "EngineeringDiagramStudio" / "logs"
        details = traceback.format_exc()
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log = log_dir / "startup-error.log"
            log.write_text(details, encoding="utf-8")
        except OSError:
            log = Path(tempfile.gettempdir()) / "EngineeringDiagramStudio-startup-error.log"
            log.write_text(details, encoding="utf-8")
        if "--self-test" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"The app could not start. Error details are saved at:\n{log}", "Engineering Diagram Studio", 16)
        sys.exit(1)
