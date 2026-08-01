import logging
import pathlib
import pygubu

PROJECT_PATH = pathlib.Path(__file__).parent
PROJECT_UI = PROJECT_PATH / "q_gui.ui"
RESOURCE_PATHS = [PROJECT_PATH]


class QGUIDialog:
    def __init__(self, master=None, dialogbox_name=None, project_path=PROJECT_PATH, project_ui=PROJECT_UI):
        self.logger = logging.getLogger(self.__class__.__name__)

        # don't even try to reuse a builder. it does seem to work.
        self.builder = builder = pygubu.Builder()
        builder.add_resource_path(project_path)
        builder.add_from_file(project_ui)
        self.mainwindow = builder.get_object(dialogbox_name, master)

        builder.connect_callbacks(self)

    def run(self):
        self.mainwindow.run()

    def on_cancel(self):
        self.logger.info("cancelled")
        self.mainwindow.destroy()

    # noinspection PyUnusedLocal
    def on_close(self, event):
        self.on_cancel()

    def on_save(self):
        """Callback linked directly to the XML button via Pygubu."""
        self.do_save()
        self.mainwindow.destroy()

    def do_save(self):
        pass
