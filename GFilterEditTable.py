import logging
import math
import tkinter as tk
from tkinter import messagebox, ttk

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, override, Iterator, Callable, Any


class ValidationException(ValueError):
    pass


class FilterMatcher(ABC):
    @abstractmethod
    def prepare(self, filter_text):
        pass

    @abstractmethod
    def matches(self, s: str, v: Any) -> bool:
        pass


class DefaultFilterMatcher(FilterMatcher):
    def __init__(self):
        self.filter_text = None

    def prepare(self, filter_text):
        self.filter_text = filter_text

    def matches(self, s: str, v: Any):
        if self.filter_text is None or len(self.filter_text) == 0:
            return True
        return self.filter_text in s


def is_numeric_type(var):
    return isinstance(var, (int, float, complex)) and not isinstance(var, bool)


class NumberFilterMatcher(FilterMatcher):
    def __init__(self):
        self.code = None
        self.expression = None
        self.ALLOWED_NAMES = {
            k: v for k, v in math.__dict__.items() if not k.startswith("__")
        }

    def prepare(self, filter_text):
        ft = filter_text
        if ft is None or len(ft) == 0:
            self.code = None
            self.expression = None
            return
        try:
            self.compile(ft)  # see if it evaluates to a constant
            v = self.evaluate()
            logging.debug("return value from testing '%s' is %s (type %s)", ft, v, type(v))
            if is_numeric_type(v):
                ft = f"x == {filter_text}"
                self.compile(ft, ['x'])
                logging.debug("got a constant! using '%s'", self.expression)
                return
        except (SyntaxError, NameError) as ex:
            logging.warning("expression '%s' failed to compile: %s", ft, ex)
            pass

        try:
            ft = f"x {filter_text}"
            self.compile(ft, ['x'])
            v = self.evaluate(0.0)
            if isinstance(v, bool):
                return
            logging.warning("didn't get a boolean from test of '%s'", ft)
        except (SyntaxError, NameError):
            pass

        self.code = None
        self.expression = None
        return

    def matches(self, s: str, v: Any):
        if self.code is None:
            return True
        return self.evaluate(s)

    def compile(self, expression, names=None):
        if names is None:
            names = []

        # https://realpython.com/python-eval-function/#minimizing-the-security-issues-of-eval
        currently_allowed_names = self.ALLOWED_NAMES.copy()
        for name in names:
            currently_allowed_names[name] = name

        self.code = None
        self.expression = None

        if len(expression) == 0:
            return

        """Evaluate a math expression."""
        # Compile the expression
        logging.debug("compiling '%s'", expression)
        code = compile(expression, "<string>", "eval")
        # Validate allowed names
        for name in code.co_names:
            if name not in currently_allowed_names:
                raise NameError(f"The use of '{name}' is not allowed")

        self.code = code
        self.expression = expression

    def evaluate(self, x=None):
        currently_allowed_names = self.ALLOWED_NAMES.copy()
        if x is not None:
            currently_allowed_names['x'] = x
        return eval(self.code, {"__builtins__": {}}, currently_allowed_names)

    def __repr__(self):
        return str(self.expression)


class TypeConverter[T](ABC):
    @abstractmethod
    def to_string(self, o: T) -> str:
        pass

    @abstractmethod
    def from_string(self, s: str) -> T:
        pass


class GetterSetter[T](ABC):
    @abstractmethod
    def do_get(self, o: T) -> T:
        pass

    @abstractmethod
    def do_set(self, o: T, v: str) -> T:
        pass


class ValueValidator[T](ABC):
    @abstractmethod
    def validate(self, v: T) -> None:
        pass


class KeyValidator(ABC):
    # noinspection PyUnusedLocal
    @abstractmethod
    def validate_key(self, proposed_text, action, inserted_char):
        return True


class DropdownProvider(ABC):
    @abstractmethod
    def provide_values(self) -> Iterator[str]:
        pass


class DataInterface(ABC):
    @abstractmethod
    def save_data(self, data):
        pass

    @abstractmethod
    def delete_data(self, data):
        pass


@dataclass
class ColumnDescription:
    label: str
    read_only: bool = False
    getter_setter: Optional[GetterSetter] = None                 # called with source object
    filter_enabled: bool = True
    width: int = 140
    minimum_width: int = 80
    anchor: str = "w"
    key_validator: Optional[KeyValidator] = None
    value_validator: Optional[ValueValidator] = None
    type_converter: Optional[TypeConverter] = None
    dropdown_provider: Optional[DropdownProvider] = None
    sort_key: Optional[Callable[[str, Any], Any]] = None
    filter_matcher: Optional[FilterMatcher] = None

    def __post_init__(self):
        assert self.label is not None
        assert self.getter_setter is not None


class FilterEditTable(ttk.Frame):
    def __init__(self, parent, column_descriptions, data_interface: Optional[DataInterface] = None):
        super().__init__(parent)
        self.column_descriptions: Optional[List[ColumnDescription]] = column_descriptions
        self.data_interface = data_interface

        self.filter_vars = {}
        self.filter_entries = {}
        self.data_store = []
        self.extra_data = {}
        self.cell_edit_entry = None

        self.filter_row = None
        self.tree = None
        self.menu = None

        self.build_widget_layout()

        self.t_item = None
        self.t_col = None

    def build_widget_layout(self):
        # 1. Main Grid Layout System
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 2. Controls Header Frame (Filters and Actions)
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.filter_row = ttk.Frame(ctrl_frame)

        # Pin Clear Button on the right
        ttk.Button(
            ctrl_frame, text="Clear Filters", command=self.clear_filters
        ).pack(side="right", padx=(5, 15))
        self.filter_row.pack(side="left", fill="x", expand=True, padx=(0, 5))

        # Build individual search fields with placeholder support
        for idx, column_description in enumerate(self.column_descriptions):
            column_label = column_description.label
            self.filter_row.grid_columnconfigure(idx, weight=1)
            var = tk.StringVar()
            self.filter_vars[column_label] = var
            entry = ttk.Entry(
                self.filter_row, textvariable=var, foreground="gray"
            )
            entry.grid(row=0, column=idx, sticky="ew", padx=2, pady=2)
            self.filter_entries[column_label] = entry

            p = f"Search {column_label}..."
            entry.insert(0, p)
            entry.bind(
                "<FocusIn>",
                lambda e, c=column_label, placeholder=p: self.focus_in(c, placeholder),
            )
            entry.bind(
                "<FocusOut>",
                lambda e, c=column_label, placeholder=p: self.focus_out(c, placeholder),
            )
            var.trace_add("write", self.filter_data)

        t_container = ttk.Frame(self)
        t_container.grid(row=1, column=0, sticky="nsew")
        t_container.grid_rowconfigure(0, weight=1)
        t_container.grid_columnconfigure(0, weight=1)

        # 4. Treeview Table Definition
        column_labels = [column_description.label for column_description in self.column_descriptions]
        self.tree = ttk.Treeview(
            t_container,
            columns=column_labels,
            show="headings",
            selectmode="extended",
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        v_scroll = ttk.Scrollbar(
            t_container, orient="vertical", command=self.tree.yview
        )
        v_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=v_scroll.set)

        #  NEW UPDATE: Symmetrical Conditional Text Alignments
        for column_description in self.column_descriptions:
            column_label = column_description.label
            self.tree.heading(column_label, text=column_label, command=lambda c=column_label: self.sort_col(c, False))
            self.tree.column(column_label, width=column_description.width, minwidth=column_description.minimum_width,
                             stretch=True, anchor=column_description.anchor)

        # 5. Right-Click Context Menu
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Copy Cell Value", command=self.copy_cell)
        self.menu.add_command(label="Copy Full Row Data", command=self.copy_row)
        # self.menu.add_separator()
        # self.menu.add_command(label="Delete Selected Row(s)", command=self.delete_rows

        # 6. Bind Interactivity
        self.bind("<Configure>", self.sync_widths)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-3>", self.show_menu)  # Windows/Linux
        self.tree.bind("<Button-2>", self.show_menu)  # macOS

        self.populate_tree()
        self.after(100, self.sync_widths)

    def focus_in(self, col, p):
        if self.filter_entries[col].get() == p:
            self.filter_entries[col].configure(foreground="black")
            self.filter_vars[col].set("")

    def focus_out(self, col, p):
        if self.filter_entries[col].get() == "":
            self.filter_entries[col].configure(foreground="gray")
            self.filter_vars[col].set(p)

    def clear_filters(self):
        """Resets all input search bars and restores original unsorted row ordering."""
        # 1. Clear text and restore placeholders in search entries
        for column_description in self.column_descriptions:
            col = column_description.label
            self.filter_entries[col].configure(foreground="gray")
            self.filter_vars[col].set(f"Search {col}...")
            # Reset header text to remove '▲' or '▼' sorting arrows
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_col(c, False))

        # 2. Re-render table using original data-entry order
        self.populate_tree()

    # noinspection PyUnusedLocal
    def sync_widths(self, event=None):
        for idx, column_description in enumerate(self.column_descriptions):
            col = column_description.label
            self.filter_row.grid_columnconfigure(idx, minsize=self.tree.column(col, "width"))

    def populate_tree(self, indices=None):
        """Deletes all items and rebuilds the tree in the strict order of self.data_store."""
        self.tree.delete(*self.tree.get_children())
        self.extra_data.clear()
        d_idx = 0
        for m_idx, data_item in enumerate(self.data_store):
            if indices is not None and m_idx not in indices:
                continue

            row = []
            for column_description in self.column_descriptions:
                # get the object
                v = column_description.getter_setter.do_get(data_item)
                if column_description.type_converter is not None:
                    s = column_description.type_converter.to_string(v)
                else:
                    if isinstance(v, str):
                        s = v
                    else:
                        s = str(v)
                row.append(s)

            row = tuple(row)

            # Re-insert items cleanly. Because we pass them sequentially by m_idx,
            # any prior visual sorting modifications are completely wiped out.
            iid = self.tree.insert("", "end", iid=m_idx, values=row, tags=("even" if d_idx % 2 == 0 else "odd",))
            self.extra_data[iid] = {"raw": data_item}
            d_idx += 1

        self.tree.tag_configure("even", background="#f2f2f2")
        self.tree.tag_configure("odd", background="#ffffff")

    # noinspection PyUnusedLocal
    def filter_data(self, *args):
        filter_matchers = []
        for column_description in self.column_descriptions:
            fm = column_description.filter_matcher
            if fm is None:
                fm = DefaultFilterMatcher()

            c_name = column_description.label
            filter_val = self.filter_vars[c_name].get()
            term = "" if filter_val == f"Search {c_name}..." else filter_val

            fm.prepare(term)

            filter_matchers.append(fm)

        indices = []
        for m_idx, row in enumerate(self.data_store):
            match = True
            for c_idx, column_description in enumerate(self.column_descriptions):
                c_name = column_description.label
                filter_val = self.filter_vars[c_name].get()
                term = "" if filter_val == f"Search {c_name}..." else filter_val
                if term and c_idx < len(self.column_descriptions):
                    row_val = column_description.getter_setter.do_get(row)
                    if column_description.filter_matcher is None:
                        column_match = term.lower() in str(row_val).lower()
                    else:
                        column_match = column_description.filter_matcher.matches(row_val, row)

                    if not column_match:
                        match = False
                        break
            if match:
                indices.append(m_idx)
        self.populate_tree(indices)

    def sort_col(self, col, rev):
        column_description = None
        for cd1 in self.column_descriptions:
            c = cd1.label
            self.tree.heading(c, text=c)
            if c == col:
                column_description = cd1
        self.tree.heading(col, text=f"{col}{' ▼' if rev else ' ▲'}")

        items = [(self.tree.set(iid, col), iid, self.extra_data[iid]) for iid in self.tree.get_children()]
        if column_description.sort_key is None:
            items.sort(key=lambda t: t[0], reverse=rev)
        else:
            items.sort(key=lambda t: column_description.sort_key(t[0], t[2]['raw']), reverse=rev)
        for index, (val, k, _) in enumerate(items):
            self.tree.move(k, "", index)
            self.tree.item(k, tags=("even" if index % 2 == 0 else "odd",))
        self.tree.heading(col, command=lambda: self.sort_col(col, not rev))

    def on_double_click(self, event):
        if self.cell_edit_entry:
            self.cell_edit_entry.destroy()
        r_id = self.tree.identify_row(event.y)
        c_id = self.tree.identify_column(event.x)
        if not r_id or not c_id:
            return

        # Calculate the zero-based numerical index of the clicked column
        c_idx = int(c_id.replace('#', '')) - 1

        column_description = self.column_descriptions[c_idx]

        # 🟢 READONLY CHECK
        if column_description.read_only:
            return  # Instantly exit the function so no inline editing widget appears

        x, y, w, h = self.tree.bbox(r_id, c_id)
        row_values = self.tree.item(r_id, 'values')
        curr = row_values[c_idx] if c_idx < len(row_values) else ""

        if column_description.dropdown_provider is not None:
            self.cell_edit_entry = ttk.Combobox(self.tree)
            self.cell_edit_entry['values'] = list(v for v in column_description.dropdown_provider.provide_values())
            if curr in self.cell_edit_entry['values']:
                self.cell_edit_entry.set(curr)
            self.cell_edit_entry.bind("<Key>", lambda e: "break")
            self.cell_edit_entry.bind("<<ComboboxSelected>>", lambda e: self.save_cell(r_id, c_idx))
            self.cell_edit_entry.bind("<FocusOut>",
                                      lambda e: self.after(100, lambda: self.check_dropdown_focus(r_id, c_idx)))
        else:  # Standard text editor
            self.cell_edit_entry = ttk.Entry(self.tree)
            self.cell_edit_entry.insert(0, curr)
            self.cell_edit_entry.select_range(0, tk.END)

            if column_description.key_validator is not None:
                vcmd = (self.register(column_description.key_validator.validate_key), '%P', '%d', '%S')
                self.cell_edit_entry.configure(validate="key", validatecommand=vcmd)

            self.cell_edit_entry.bind("<Return>", lambda e: self.save_cell(r_id, c_idx))
            self.cell_edit_entry.bind("<FocusOut>", lambda e: self.save_cell(r_id, c_idx))

        self.cell_edit_entry.focus_set()
        self.cell_edit_entry.place(x=x, y=y, width=w, height=h)
        self.cell_edit_entry.bind("<Escape>", lambda e: self.cell_edit_entry.destroy())

        if column_description.dropdown_provider is not None:
            self.after(50, lambda: self.tk.call('ttk::combobox::Post', self.cell_edit_entry))

    def check_dropdown_focus(self, r_id, c_idx):
        if not self.cell_edit_entry or not self.cell_edit_entry.winfo_exists():
            return
        if "pressed" in self.cell_edit_entry.state():
            return
        self.save_cell(r_id, c_idx)

    def save_cell(self, r_id, c_idx):
        if not self.cell_edit_entry or not self.cell_edit_entry.winfo_exists():
            return
        val_string = self.cell_edit_entry.get().strip()

        column_description = self.column_descriptions[c_idx]

        try:
            if column_description.type_converter is not None:
                val = column_description.type_converter.from_string(val_string)
                new_val_string = column_description.type_converter.to_string(val)
            else:
                val = val_string
                new_val_string = val

            if column_description.value_validator is not None:
                column_description.value_validator.validate(val)

        except ValueError as ve:
            # If the string fails to resolve to a value, or fails validation, block saving and alert user
            messagebox.showerror("Validation Error", str(ve))
            self.cell_edit_entry.focus_set()
            return  # Halts execution so the editor frame stays open for correction

        # Standard baseline logic continues if validation checks pass
        value_strings = list(self.tree.item(r_id, 'values'))
        if c_idx < len(value_strings):
            value_strings[c_idx] = new_val_string
        else:
            logging.warning("set_cell got index that was too high")
        self.tree.item(r_id, values=value_strings)

        m_idx = int(r_id)

        data_item = self.data_store[m_idx]
        data_item = column_description.getter_setter.do_set(data_item, val)
        self.data_store[m_idx] = data_item
        self.save_row(self.data_store[m_idx])

        self.cell_edit_entry.destroy()
        self.cell_edit_entry = None
        self.filter_data()
        if hasattr(self.master, 'update_toolbar_metrics'):
            self.master.update_toolbar_metrics()

    def show_menu(self, event):
        try:
            item = self.tree.identify_row(event.y)
            if item:
                self.t_item, self.t_col = item, self.tree.identify_column(event.x)
                if item not in self.tree.selection():
                    self.tree.selection_set(item)
                self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def copy_cell(self):
        if hasattr(self, 't_item') and hasattr(self, 't_col'):
            c_idx = int(self.t_col.replace('#', '')) - 1
            vals = self.tree.item(self.t_item, "values")
            if 0 <= c_idx < len(vals):
                self.clipboard_clear()
                self.clipboard_append(vals[c_idx])

    def copy_row(self):
        lines = ["\t".join(self.tree.item(i, "values")) for i in self.tree.selection()]
        if lines:
            self.clipboard_clear()
            self.clipboard_append("\n".join(lines))

    def delete_rows(self):
        sel = self.tree.selection()
        if sel and messagebox.askyesno("Confirm", f"Delete {len(sel)} row(s)?"):
            for idx in sorted([int(i) for i in sel], reverse=True):
                item_to_delete = self.data_store[idx]
                self.data_store.pop(idx)
                self.delete_row(item_to_delete)
            self.filter_data()
            if hasattr(self.master, 'update_toolbar_metrics'):
                self.master.update_toolbar_metrics()

    def save_row(self, row):
        if self.data_interface is not None:
            self.data_interface.save_data(row)

    def delete_row(self, row):
        if self.data_interface is not None:
            self.data_interface.delete_data(row)


class IntTypeConverter(TypeConverter):
    @override
    def to_string(self, o: int) -> str:
        return str(o)

    @override
    def from_string(self, s: str) -> int:
        return int(s)


class TGS(GetterSetter[tuple]):
    def __init__(self, i):
        assert isinstance(i, int)
        self.i = i

    @override
    def do_get(self, o: tuple) -> str:
        assert isinstance(o, tuple)
        return o[self.i]

    @override
    def do_set(self, o: tuple, v) -> tuple:
        assert isinstance(o, tuple)
        o_copy = list(o)
        o_copy[self.i] = v
        return tuple(o_copy)


class CGS(GetterSetter):
    def __init__(self, name):
        assert isinstance(name, str)
        self.name = name

    @override
    def do_get(self, o) -> str:
        assert hasattr(o, self.name), f"Object {o} has no attribute {self.name}"
        return getattr(o, self.name)

    @override
    def do_set(self, o: tuple, v):
        setattr(o, self.name, v)
        return o


class DGS(GetterSetter):
    def __init__(self, name):
        assert isinstance(name, str)
        self.name = name

    @override
    def do_get(self, o) -> str:
        return o[self.name]

    @override
    def do_set(self, o: dict, v):
        o[self.name] = v
        return o


class CodeAndTextContainer(TypeConverter, DropdownProvider):
    def __init__(self):
        self.code_to_text_dict = {}
        self.text_to_code_dict = {}

    def add(self, code, text):
        self.code_to_text_dict[code] = text
        self.text_to_code_dict[text] = code

    @override
    def provide_values(self) -> Iterator[str]:
        for code in sorted(self.text_to_code_dict.keys()):
            yield code

    @override
    def to_string(self, o: str) -> str:
        return self.code_to_text_dict.get(o)

    @override
    def from_string(self, s: str) -> str:
        return self.text_to_code_dict.get(s)
