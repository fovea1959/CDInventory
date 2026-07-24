#!/usr/bin/python3

import csv
import json
import queue
import sys

from dataclasses import dataclass, asdict

from logging.handlers import RotatingFileHandler

from tkinter import font as tkfont
from typing import override

from pythonjsonlogger.json import JsonFormatter

import utils

from CDInventoryDao import DAO
from CDInventoryEntities import CD, Location

from GFilterEditTable import *

from q_gui_generic_app import QGuiGenericApp


PREFS_FILE_NAME = "q_gui_prefs.json"


@dataclass
class Preferences:
    gui_geometry: str | None = None
    gui_panedwindow1_sash: int | None = None


class G:
    def __init__(self):
        self.gui: QGuiApp | None = None
        self.mb = utils.MB()
        self.preferences = Preferences()


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

        self.setup_cds_frame()

        self.mainwindow = self.builder.get_object("tk1", master)
        self.panedwindow1 = self.builder.get_object("panedwindow1", master)
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

    def on_close(self):
        self.g.preferences.gui_geometry = self.mainwindow.geometry()
        self.g.preferences.gui_panedwindow1_sash = self.panedwindow1.sashpos(0)
        self.mainwindow.destroy()

    @override
    def menuitem_test(self, itemid):
        self.logger.important("menuitem_test hit: %s", itemid)

    def setup_cds_frame(self):
        d = []
        locations = set()
        with open('c3.csv', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                d.append(row)
                locations.add(row['location_description'])
        locations = sorted(locations)

        dropdown_converter = CodeAndTextContainer()
        for location in locations:
            dropdown_converter.add(location, location + "!")

        column_descriptions = [
            ColumnDescription(label="Title", read_only=True, getter_setter=DGS("cd_title")),
            ColumnDescription(label="Artist", read_only=True, getter_setter=DGS("cd_artists")),
            ColumnDescription(label="Location", getter_setter=DGS("location_description"),
                                dropdown_provider=dropdown_converter,
                                type_converter=dropdown_converter),
        ]

        # Component Initialization
        tab_container = self.builder.get_object("cd_frame")
        table_widget = FilterEditTable(tab_container, column_descriptions=column_descriptions)
        # table_widget.data_interface = GFilterEditTable.ObjectDataInterface(filter_edit_table=table_widget, filename="GFilterEditTable.csv", clazz=dict)

        table_widget.data_store = d
        table_widget.populate_tree()

        table_widget.pack(fill="both", expand=True)

    def run(self):
        self.running = True
        self.logger.info("starting")
        super().run()
        self.running = False
        self.logger.info("finished")

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


VERBOSE_LEVEL_NUM = 15
IMPORTANT_LEVEL_NUM = 25


def verbose(self, message, *args, **kws):
    if self.isEnabledFor(VERBOSE_LEVEL_NUM):
        # Yes, logger._log is a semi-private API, but this is the standard way
        self._log(VERBOSE_LEVEL_NUM, message, args, **kws)


def important(self, message, *args, **kws):
    if self.isEnabledFor(IMPORTANT_LEVEL_NUM):
        # Yes, logger._log is a semi-private API, but this is the standard way
        self._log(IMPORTANT_LEVEL_NUM, message, args, **kws)


def setup_custom_log_level():
    logging.addLevelName(VERBOSE_LEVEL_NUM, "VERBOSE")
    logging.Logger.verbose = verbose
    logging.addLevelName(IMPORTANT_LEVEL_NUM, "IMPORTANT")
    logging.Logger.important = important


def main(argv):
    setup_custom_log_level()

    logger = logging.getLogger('')
    logger.setLevel(VERBOSE_LEVEL_NUM)

    file_handler = RotatingFileHandler(
        "q_gui.log",
        maxBytes=(10 * 1024 * 1024),
        backupCount=5
    )
    file_handler.setFormatter(JsonFormatter(
        fmt="{levelname} {message} {name} {asctime} {threadName} {levelno}", style="{"
    ))
    file_handler.setLevel(VERBOSE_LEVEL_NUM)
    logger.addHandler(file_handler)

    log_queue = queue.Queue()
    queue_handler = utils.QueueHandler(log_queue=log_queue)
    queue_handler.setLevel(IMPORTANT_LEVEL_NUM)
    logger.addHandler(queue_handler)

    g = G()
    try:
        with open(PREFS_FILE_NAME, "r") as f:
            data = json.load(f)
            g.preferences = Preferences(**data)
    except Exception as exc:
        logger.warning("unable to load prefs from %s: %s", PREFS_FILE_NAME, exc)

    try:
        app = QGuiApp(g=g, log_queue=log_queue)
        app.run()
    except KeyboardInterrupt:
        logger.important("received KeyboardInterrupt")
    except Exception as exc:
        logger.error("received %s", exc, exc_info=exc)
    finally:
        logger.important("telling everyone to die")
        g.die = True

    with open(PREFS_FILE_NAME, "w") as f:
        json.dump(asdict(g.preferences), f)

    logger.info('all done!')


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)-9s %(name)-15s %(message)s")
    main(sys.argv[1:])
