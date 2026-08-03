#!/usr/bin/python3
import collections
import json
import datetime
import pathlib
import queue
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

# noinspection PyUnresolvedReferences
from dataclasses import asdict, dataclass

from logging.handlers import RotatingFileHandler

from tkinter import font as tkfont
from tkinter import filedialog

import pygubu

import sqlalchemy
from pythonjsonlogger.json import JsonFormatter

import cd_inventory_dao
import mp3_information_extractor
import utils

from cd_inventory_entities import CD, MP3
from generic_filter_edit_table import *
from q_gui_dialog import *


PREFS_FILE_NAME = "q_gui_prefs.json"

PROJECT_PATH = pathlib.Path(__file__).parent
PROJECT_UI = PROJECT_PATH / "q_gui.ui"
RESOURCE_PATHS = [PROJECT_PATH]


@dataclass
class Preferences:
    mp3_path: str | None = None
    mp3u_file: str | None = None
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


class QGuiApp:
    def __init__(self, master=None, g: G = None, log_queue: queue.Queue = None, logging_formatter=None):
        self.builder = builder = pygubu.Builder()
        builder.add_resource_path(PROJECT_PATH)
        builder.add_from_file(PROJECT_UI)
        self.mainwindow = builder.get_object("mainwindow", master)
        builder.connect_callbacks(self)

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

        self.m_mp3s = self.builder.get_object("m_mp3s")

        self.cds_frame = self.setup_cds_frame()
        self.mp3s_frame = self.setup_mp3s_frame()
        self.unripped_cds_frame = self.setup_unripped_cds_frame()

        self.status_text_var = self.builder.get_variable("status_text")

        self.panedwindow1 = self.builder.get_object("panedwindow1", master)

        self.setup_window()
        self.mainwindow.protocol("WM_DELETE_WINDOW", self.on_close)

        self.logger.info("__init__ successful")

    def run(self):
        self.mainwindow.mainloop()

    def on_cmd_quit(self):
        self.on_close()

    def on_cmd_preferences(self):
        # Create dialog window.
        # dialog = BadPreferencesDialog(self.mainwindow, g=G())
        dialog = PrefsDialog(self.mainwindow, g=self.g)
        dialog.run()
        # Dialog was configured to run in modal state.
        # So wait until the window is closed.
        self.mainwindow.wait_window(dialog.mainwindow.toplevel)

    def setup_window(self):
        gui_geometry = self.g.preferences.gui_geometry
        if gui_geometry is not None:
            self.mainwindow.geometry(gui_geometry)
        # Restore paned window sash position with a slight delay
        gui_panedwindow1_sash = self.g.preferences.gui_panedwindow1_sash
        if gui_panedwindow1_sash is not None:
            self.mainwindow.after(50, lambda: self.panedwindow1.sashpos(0, gui_panedwindow1_sash))

        self.cds_frame.set_widths(self.g.preferences.gui_cd_column_widths)
        self.mp3s_frame.set_widths(self.g.preferences.gui_mp3_column_widths)
        self.unripped_cds_frame.set_widths(self.g.preferences.gui_unripped_cd_column_widths)

    def on_close(self):
        self.logger.important("saving preferences")
        self.g.preferences.gui_geometry = self.mainwindow.geometry()
        self.g.preferences.gui_panedwindow1_sash = self.panedwindow1.sashpos(0)
        self.g.preferences.gui_cd_column_widths = self.cds_frame.get_widths()
        self.g.preferences.gui_mp3_column_widths = self.mp3s_frame.get_widths()
        self.g.preferences.gui_unripped_cd_column_widths = self.unripped_cds_frame.get_widths()
        self.mainwindow.destroy()

    def on_cmd_about(self):
        pass

    def on_cmd_save_playlist_newest_first(self):
        if self.g.preferences.mp3u_file is not None:
            mp3u_path = pathlib.Path(self.g.preferences.mp3u_file)
            initialdir = mp3u_path.parent
            initialfile = mp3u_path.name
        elif self.g.preferences.mp3_path is not None:
            initialdir = pathlib.Path(self.g.preferences.mp3_path)
            initialfile = ''
        else:
            initialdir = ''
            initialfile = ''
        # Opens the file selector and returns the absolute file path as a string
        file_path = filedialog.asksaveasfilename(
            title="Save playlist (newest recordings first)",
            initialdir=initialdir,
            initialfile=initialfile,
            filetypes=[("MP3 playlists", "*.m3u"), ("All files", "*.*")]
        )
        if file_path:
            self.g.preferences.mp3u_file = file_path
            self.logger.info("Saving MP3U to %s", file_path)

            l_mp3 = []
            self.logger.info("Fetching mp3s")
            for mp3 in self.g.dao.get_all_mp3s():
                l_mp3.append(mp3)
            self.logger.info("Sorting mp3s")
            l_mp3 = utils.sort_mp3s_newest_first(l_mp3)
            self.logger.info("Writing mp3s")
            with open(file_path, "w") as f:
                for mp3 in l_mp3:
                    print(f'# {mp3.age_sort_key()} {mp3.encoded_time} {mp3.mtime}', file=f)
                    print(mp3.path, file=f)
            self.logger.info("Done")

    def on_cmd_load_mp3s(self):
        self.logger.important("loading mp3s")
        self.status_text_var.set("Loading mp3s")

        self.m_mp3s.entryconfig("Load MP3s", state="disabled")
        # self.btn.config(state="disabled")
        # self.status.config(text="Loading data from database...")
        # self.result_label.config(text="")

        # 2. Run slow query in a background thread
        threading.Thread(target=self.load_mp3s, daemon=True).start()

    def load_mp3s(self):
        dao = cd_inventory_dao.DAO()
        with dao:
            now = datetime.datetime.now().astimezone()
            root_path = pathlib.Path(self.g.preferences.mp3_path)
            x = mp3_information_extractor.MP3InfoExtractor(root_path)
            last_dirpath = None
            counts = collections.Counter()
            all_mp3_path_strings = set()
            for dirpath, dirname, filenames in root_path.walk():
                if dirpath != last_dirpath:
                    self.status_text_var.set(f"Loading {dirpath}")
                    last_dirpath = dirpath
                for f1 in filenames:
                    counts['total files'] += 1
                    if not str(f1).lower().endswith(".mp3"):
                        counts['not MP3'] += 1
                        continue

                    p1 = dirpath / f1
                    r_p1 = p1.relative_to(root_path)
                    mp3 = dao.get_mp3_by_path(str(r_p1))

                    counts['mp3s'] += 1
                    all_mp3_path_strings.add(str(r_p1))

                    need_to_update = False
                    if mp3 is None:
                        need_to_update = True
                    else:
                        mtime = datetime.datetime.fromtimestamp(p1.stat().st_mtime)
                        wuz = mp3.updated_time
                        if mtime > wuz:
                            self.logger.info('%s: mtime %s, database updated %s, so updating', r_p1, mtime, wuz)
                            need_to_update = True

                    if need_to_update:
                        j = x.get_information(p1)
                        if j is None:
                            self.logger.important("Can't get MP3 tags from %s", p1)
                            counts['MP3s w/ no tags'] += 1
                        else:
                            iz_new = False
                            if mp3 is None:
                                mp3 = MP3()
                                iz_new = True
                            mp3_information_extractor.fill_in_mp3_from_dict(mp3, j)
                            mp3.updated_time = now
                            if iz_new:
                                counts['MP3s created'] += 1
                                dao.session.add(mp3)
                            else:
                                counts['MP3s updated'] += 1
                            if (counts['MP3s created'] + counts['MP3s updated']) % 100 == 0:
                                dao.session.commit()
                    else:
                        counts['MP3s up-to-date'] += 1
            dao.session.commit()
            self.logger.important("had %d MP3s", len(all_mp3_path_strings))

            # now need to get rid of old mp3s
            for mp3 in dao.get_all_mp3s():
                if mp3.path not in all_mp3_path_strings:
                    dao.session.delete(mp3)
                    counts['MP3s deleted'] += 1
                    if counts['MP3s deleted'] % 100 == 0:
                        dao.session.commit()
            dao.session.commit()

            m = f"MP3 load completed: {counts}"
            self.logger.important(m)
            # 3. Safely send results back to main thread using root.after
            self.mainwindow.after(0, self.mp3_load_done, m)

    def mp3_load_done(self, m):
        # self.logger.important("slow query complete: %s", data)
        self.status_text_var.set(m)
        # self.toast(data, 10)
        self.m_mp3s.entryconfig("Load MP3s", state="normal")
        pass

    def get_cd_for_command(self, fte: FilterEditTable):
        cd: CD | None = None
        data_row: dict = fte.get_data_for_right_menu_click()
        self.logger.info("Right click from %s", data_row)
        if data_row is not None:
            cd = data_row.get('raw')
        return cd

    def request_url(self, url):
        try:
            # Send the GET request with a 5-second timeout
            with urllib.request.urlopen(url, timeout=5) as response:
                # Read the raw bytes and decode to a string
                raw_data = response.read().decode('utf-8')
                self.logger.info("GET %s success: %s", url, raw_data)

        except urllib.error.HTTPError as e:
            self.logger.error("GET %s HTTP error: %s - %s", url, e.code, e.reason)
        except urllib.error.URLError as e:
            self.logger.error("GET %s Connection error: %s", url, e.reason)

    def command_send_release_id_to_picard(self, fte: FilterEditTable):
        cd = self.get_cd_for_command(fte)
        if cd is not None:
            release_id = cd.cd_musicbrainz_release_id
            self.logger.info("Sending release %s to picard", release_id)
            url = f"http://127.0.0.1:8000/openalbum?id={release_id}"
            self.request_url(url)

    def command_open_musicbrainz_for_this_release(self, fte: FilterEditTable):
        cd = self.get_cd_for_command(fte)
        if cd is not None:
            release_id = cd.cd_musicbrainz_release_id
            self.logger.info("Opening release %s in browser", release_id)
            url = f"https://musicbrainz.org/release/{release_id}"
            webbrowser.open(url)

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
        table_widget.menu.add_command(label="Open Musicbrainz for this release",
                                      command=lambda: self.command_open_musicbrainz_for_this_release(table_widget))
        table_widget.menu.add_command(label="Send release id to Picard",
                                      command=lambda: self.command_send_release_id_to_picard(table_widget))

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


class PrefsDialog(QGUIDialog):
    def __init__(self, master=None, g: G = None):
        super().__init__(master=master, dialogbox_name="preferences_dialog")
        self.g = g
        self.prefs_mp3_path_widget = self.builder.get_object("mp3_path_widget")
        current_path = self.g.preferences.mp3_path
        if current_path is not None:
            self.prefs_mp3_path_widget.configure(initialdir=current_path)
            self.prefs_mp3_path_widget.configure(path=current_path)

    @override
    def do_save(self):
        self.g.preferences.mp3_path = self.prefs_mp3_path_widget.cget('path')
        self.logger.important("Saving settings: %s", self.g.preferences.mp3_path)


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

    logging.info("prefs: %s", g.preferences)

    g.dao = cd_inventory_dao.DAO()

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
