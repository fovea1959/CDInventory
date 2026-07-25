#!/usr/bin/python3

import json
import queue
import sys
import threading

# noinspection PyUnresolvedReferences
from dataclasses import asdict, dataclass

from logging.handlers import RotatingFileHandler

from tkinter import font as tkfont

import sqlalchemy
from pythonjsonlogger.json import JsonFormatter

import CDInventoryDao
import GFilterEditTable
import utils
from CDInventoryEntities import CD

from GFilterEditTable import *

from q_gui_generic_app import QGuiGenericApp

PREFS_FILE_NAME = "q_gui_prefs.json"


@dataclass
class Preferences:
    gui_geometry: str | None = None
    gui_panedwindow1_sash: int | None = None
    gui_cd_column_widths: List[int] | None = None
    gui_mp3_column_widths: List[int] | None = None
    gui_unripped_cd_column_widths: List[int] | None = None


class G:
    def __init__(self):
        self.gui: QGuiApp | None = None
        self.mb = utils.MB()
        self.preferences = Preferences()
        self.dao = None


class EntityDataInterface(DataInterface):
    def __init__(self, g=None):
        self.g = g
        self.logger = logging.getLogger(self.__class__.__name__)

    @override
    def save_data(self, data):
        for obj in self.g.dao.session.dirty:
            inspector = sqlalchemy.inspect(obj)

            pk_value = inspector.identity or "Transient"

            for attr in inspector.attrs:
                if attr.history.has_changes():
                    self.logger.important("%s (PK: %s) -> '%s' changed: %s ➡ %s",
                                          obj.__class__.__name__, pk_value, attr.key, attr.history.deleted, attr.value)

        self.g.dao.session.commit()

    @override
    def delete_data(self, data):
        raise Exception("shouldn't get called")


class ReadOnlyDataInterface(DataInterface):
    def __init__(self, g=None):
        self.g = g
        self.logger = logging.getLogger(self.__class__.__name__)

    @override
    def save_data(self, data):
        raise Exception("readonly!")

    @override
    def delete_data(self, data):
        raise Exception("readonly!")


class LocationDescriptionGS(GetterSetter):
    def do_get(self, o: CD) -> str:
        return o.cd_location.location_description

    def do_set(self, o: CD, v: str) -> CD:
        raise Exception("no do_set!")


class QGuiApp(QGuiGenericApp):
    def __init__(self, master=None, g: G = None, log_queue: queue.Queue = None, logging_formatter=None):
        super().__init__(master)
        self.master = master
        self.g = g
        g.gui = self
        self.logger = logging.getLogger(self.__class__.__name__)

        self.log_text = self.builder.get_object('log_text', master)
        current_font = tkfont.Font(font=self.log_text.cget("font"))
        bold_font = tkfont.Font(family=current_font.actual("family"), size=current_font.actual("size"), weight="bold")
        self.log_text.tag_configure("warning", foreground="red")
        self.log_text.tag_configure("error", foreground="red", font=bold_font)
        self.log_queue = log_queue
        self.logging_formatter = logging_formatter if logging_formatter \
            else logging.Formatter('%(levelname)s %(name)s %(message)s')
        self.mainwindow.after(100, self.poll_log_queue)

        self.mainwindow = self.builder.get_object("tk1", master)
        self.panedwindow1 = self.builder.get_object("panedwindow1", master)

        self.cds_frame = self.setup_cds_frame()
        self.mp3s_frame = self.setup_mp3s_frame()
        self.unripped_cds_frame = self.setup_unripped_cds_frame()

        self.setup_window()
        self.mainwindow.protocol("WM_DELETE_WINDOW", self.on_close)

        self.logger.info("__init__ successful")

    def setup_window(self):
        gui_geometry = self.g.preferences.gui_geometry
        if gui_geometry is not None:
            self.mainwindow.geometry(gui_geometry)
        # Restore paned window sash position with a slight delay
        gui_panedwindow1_sash = self.g.preferences.gui_panedwindow1_sash
        if gui_panedwindow1_sash is not None:
            self.mainwindow.after(50, lambda: self.panedwindow1.sashpos(0, gui_panedwindow1_sash))

        self.logger.info("prefs: %s", self.g.preferences)

        self.cds_frame.set_widths(self.g.preferences.gui_cd_column_widths)
        self.mp3s_frame.set_widths(self.g.preferences.gui_mp3_column_widths)
        self.unripped_cds_frame.set_widths(self.g.preferences.gui_unripped_cd_column_widths)

    def on_close(self):
        self.g.preferences.gui_geometry = self.mainwindow.geometry()
        self.g.preferences.gui_panedwindow1_sash = self.panedwindow1.sashpos(0)
        self.g.preferences.gui_cd_column_widths = self.cds_frame.get_widths()
        self.g.preferences.gui_mp3_column_widths = self.mp3s_frame.get_widths()
        self.g.preferences.gui_unripped_cd_column_widths = self.unripped_cds_frame.get_widths()
        self.mainwindow.destroy()

    @override
    def menuitem_test(self, itemid):
        self.logger.important("menuitem_test hit: %s", itemid)

        # self.btn.config(state="disabled")
        # self.status.config(text="Loading data from database...")
        # self.result_label.config(text="")

        # 2. Run slow query in a background thread
        threading.Thread(target=self.fetch_query, daemon=True).start()

    def fetch_query(self):
        try:
            # Simulate or execute slow SQLAlchemy query here
            # result = session.query(MyModel).all()
            import time
            time.sleep(3)  # Simulating a 3-second slow query
            data = "Query finished successfully!"
        except Exception as e:
            data = f"Error: {e}"

        self.logger.important("query done")
        # 3. Safely send results back to main thread using root.after
        self.mainwindow.after(0, self.update_ui, data)

    def update_ui(self, data):
        self.logger.important("slow query complete: %s", data)
        self.toast(data, 10)

    def command_send_release_id_to_picard(self, fte: GFilterEditTable.FilterEditTable):
        if hasattr(fte, 't_item') and hasattr(fte, 't_col'):
            c_idx = int(fte.t_col.replace('#', '')) - 1
            vals = fte.tree.item(fte.t_item, "values")
            data_row = fte.extra_data.get(fte.t_item)
            self.logger.info('%s %s', vals, data_row)

    def setup_cds_frame(self):
        d = []

        for cd in self.g.dao.get_all_cds():
            d.append(cd)

        dropdown_converter = CodeAndTextContainer()
        for location in self.g.dao.get_all_locations():
            dropdown_converter.add(location.location_id, location.location_description)

        column_descriptions = [
            ColumnDescription(label="Title", read_only=True, getter_setter=CGS("cd_title")),
            ColumnDescription(label="Artist", read_only=True, getter_setter=CGS("cd_artists")),
            ColumnDescription(label="Location", getter_setter=CGS("cd_location_id"),
                              dropdown_provider=dropdown_converter, type_converter=dropdown_converter
                              ),
        ]

        # Component Initialization
        tab_container = self.builder.get_object("cd_frame")
        table_widget = FilterEditTable(tab_container, column_descriptions=column_descriptions)
        table_widget.data_interface = EntityDataInterface(g=self.g)

        table_widget.menu.add_separator()
        table_widget.menu.add_command(label="Send release id to Picard", command=lambda: self.command_send_release_id_to_picard(table_widget))

        table_widget.data_store = d
        table_widget.populate_tree()

        table_widget.pack(fill="both", expand=True)

        return table_widget

    def setup_mp3s_frame(self):
        d = []

        for mp3 in self.g.dao.get_all_mp3s():
            d.append(mp3)

        column_descriptions = [
            ColumnDescription(label="Path", read_only=True, getter_setter=CGS("path")),
            ColumnDescription(label="Title", read_only=True, getter_setter=CGS("title")),
            ColumnDescription(label="Artists", read_only=True, getter_setter=CGS("track_artists")),
            ColumnDescription(label="Release Id", read_only=True, getter_setter=CGS("release_id")),
            ColumnDescription(label="Recording Id", read_only=True, getter_setter=CGS("recording_id")),
        ]

        # Component Initialization
        tab_container = self.builder.get_object("mp3_frame")
        table_widget = FilterEditTable(tab_container, column_descriptions=column_descriptions)
        table_widget.data_interface = ReadOnlyDataInterface(g=self.g)

        table_widget.menu.add_separator()
        table_widget.menu.add_command(label="Boo!")

        table_widget.data_store = d
        table_widget.populate_tree()

        table_widget.pack(fill="both", expand=True)

        return table_widget

    def setup_unripped_cds_frame(self):
        d = []

        for cd in self.g.dao.get_all_unripped_cds():
            d.append(cd)

        dropdown_converter = CodeAndTextContainer()
        for location in self.g.dao.get_all_locations():
            dropdown_converter.add(location.location_id, location.location_description)

        column_descriptions = [
            ColumnDescription(label="Title", read_only=True, getter_setter=CGS("cd_title")),
            ColumnDescription(label="Artist", read_only=True, getter_setter=CGS("cd_artists")),
            ColumnDescription(label="Release Id", read_only=True, getter_setter=CGS("cd_musicbrainz_release_id")),
            ColumnDescription(label="Location", read_only=True, getter_setter=CGS("cd_location_id"),
                              dropdown_provider=dropdown_converter, type_converter=dropdown_converter
                              ),
        ]

        # Component Initialization
        tab_container = self.builder.get_object("unripped_cd_frame")
        table_widget = FilterEditTable(tab_container, column_descriptions=column_descriptions)
        table_widget.data_interface = ReadOnlyDataInterface(g=self.g)

        table_widget.data_store = d
        table_widget.populate_tree()

        table_widget.pack(fill="both", expand=True)

        return table_widget

    def toast(self, message, duration):
        # Create a borderless popup window
        toast = tk.Toplevel(self.mainwindow)
        toast.overrideredirect(True)

        # Style the window
        toast.config(bg="#333333")
        label = tk.Label(toast, text=message, fg="white", bg="#333333", padx=15, pady=10, font=("Arial", 10))
        label.pack()

        # Position the toast window relative to the main window
        self.mainwindow.update_idletasks()
        x = self.mainwindow.winfo_x() + (self.mainwindow.winfo_width() // 2) - (toast.winfo_reqwidth() // 2)
        y = self.mainwindow.winfo_y() + self.mainwindow.winfo_height() - 70
        toast.geometry(f"+{x}+{y}")

        # Automatically close the toast window after the delay
        toast.after(duration, toast.destroy)

    def poll_log_queue(self):
        """Checks the queue and writes records to the text widget."""
        while True:
            try:
                # Look for records without blocking the GUI loop
                record = self.log_queue.get_nowait()
            except queue.Empty:
                break
            else:
                # Format and append message to widget
                message = self.logging_formatter.format(record)

                self.log_text.configure(state='normal')
                tag = record.levelname.lower()
                self.log_text.insert(tk.END, message + '\n', tag)
                self.log_text.configure(state='disabled')

                # Autoscroll to the absolute bottom
                self.log_text.yview(tk.END)

        # Re-queue this polling method after 100 milliseconds
        self.mainwindow.after(100, self.poll_log_queue)


# noinspection PyUnusedLocal
def main(argv):
    utils.setup_custom_log_levels()

    logger = logging.getLogger('')
    logger.setLevel(utils.VERBOSE_LEVEL_NUM)

    file_handler = RotatingFileHandler(
        "q_gui.log",
        maxBytes=(10 * 1024 * 1024),
        backupCount=5
    )
    file_handler.setFormatter(JsonFormatter(
        fmt="{levelname} {message} {name} {asctime} {threadName} {levelno}", style="{"
    ))
    file_handler.setLevel(utils.VERBOSE_LEVEL_NUM)
    logger.addHandler(file_handler)

    log_queue = queue.Queue()
    queue_handler = utils.QueueHandler(log_queue=log_queue)
    queue_handler.setLevel(utils.IMPORTANT_LEVEL_NUM)
    logger.addHandler(queue_handler)

    g = G()

    try:
        with open(PREFS_FILE_NAME, "r") as f:
            data = json.load(f)
            g.preferences = Preferences(**data)
    except Exception as exc:
        logger.warning("unable to load prefs from %s: %s", PREFS_FILE_NAME, exc)

    g.dao = CDInventoryDao.DAO()

    with g.dao:
        try:
            app = QGuiApp(g=g, log_queue=log_queue)
            app.run()
        except KeyboardInterrupt:
            logger.important("received KeyboardInterrupt")
        except Exception as exc:
            logger.error("received %s", exc, exc_info=exc)

    with open(PREFS_FILE_NAME, "w") as f:
        json.dump(asdict(g.preferences), f, indent=1, sort_keys=True)

    logger.info('all done!')


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)-9s %(name)-15s %(message)s")
    main(sys.argv[1:])
