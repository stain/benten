"""These are functions to generate edit operations on a YAML (Ydict) document."""
from typing import Tuple
from abc import ABC, abstractmethod
from enum import IntEnum, IntFlag, auto

from ..implementationerror import ImplementationError
from .edit import EditMark, Edit
from .lineloader import parse_yaml_with_line_info, YNone, Ystr, Ydict, DocumentError


class Contents(IntEnum):
    Unchanged = auto()
    Changed = auto()
    ParseSkipped = auto()
    ParseSuccess = auto()
    ParseFail = auto()


class TextType(IntEnum):
    process = 1
    documentation = 2
    expression = 3


class BaseDoc(ABC):

    def __init__(self, raw_text):
        self.raw_text = raw_text
        self.raw_lines = raw_text.splitlines(keepends=True)

    def identical_to(self, raw_text: str):
        return self.raw_text == raw_text

    def set_raw_text(self, raw_text: str):
        if self.identical_to(raw_text):
            return Contents.Unchanged
        else:
            self.raw_text = raw_text
            self.raw_lines = raw_text.splitlines(keepends=True)
            return Contents.Changed

    @abstractmethod
    def set_raw_text_and_reparse(self, raw_text: str) -> Contents:
        pass


class PlainText(BaseDoc):

    def set_raw_text_and_reparse(self, raw_text: str) -> Contents:
        return self.set_raw_text(raw_text) | Contents.ParseSkipped


class YamlDoc(BaseDoc):
    def __init__(self, raw_text):
        super().__init__(raw_text)
        self.yaml = None
        self.last_good_yaml = None
        self.yaml_error = None

    def parsed(self):
        return self.yaml is not None

    def has_yaml_errors(self):
        return self.yaml_error is not None

    def set_raw_text(self, raw_text: str):
        if super().set_raw_text(raw_text) == Contents.Unchanged:
            return Contents.Unchanged
        else:
            self.yaml = None
            self.yaml_error = None
            return Contents.Changed

    def set_raw_text_and_reparse(self, raw_text: str):
        if self.set_raw_text(raw_text) == Contents.Unchanged:
            if self.parsed():
                return Contents.Unchanged | Contents.ParseSkipped

        return self.parse_yaml() | Contents.Changed

    def parse_yaml(self):
        if self.yaml is not None and self.yaml_error is None:
            return Contents.ParseSkipped

        try:
            self.yaml = parse_yaml_with_line_info(self.raw_text, convert_to_lam=True) or Ydict.empty()
            self.yaml_error = None
            self.last_good_yaml = self.yaml
            return Contents.ParseSuccess
        except DocumentError as e:
            self.yaml_error = e
            return Contents.ParseFail

    def __contains__(self, path: Tuple[str, ...]):
        sub_doc = self.yaml
        for p in path or []:
            if not isinstance(sub_doc, dict):
                return False
            if p in sub_doc:
                sub_doc = sub_doc[p]
            else:
                return False
        else:
            return True

    def __getitem__(self, path: Tuple[str, ...]):
        sub_doc = self.yaml
        for p in path or []:
            sub_doc = sub_doc[p]
        return sub_doc

    @staticmethod
    def infer_section_type(path: Tuple[str, ...]):
        if len(path) > 0:
            if path[-1] == "run":
                return TextType.process
            else:
                return TextType.documentation
        else:
            return TextType.documentation

    def get_raw_text_for_section(self, path: Tuple[str, ...]):
        value = self[path]

        start_line, end_line = value.start.line, value.end.line
        sl = start_line
        indent_level = len(self.raw_lines[sl]) - len(self.raw_lines[sl].lstrip())

        if isinstance(value, Ydict):  # Currently, sole use case is in steps
            if value.flow_style:
                if value == {}:
                    return ""
                else:
                    raise UnableToCreateView("Flow style elements can not be edited in a view")
        elif isinstance(value, Ystr):  # Single line expressions and documentation
            # todo: check for expressions
            if value.style == "":
                return value

        lines_we_need = self.raw_lines[start_line:end_line]
        lines = [
            l[indent_level:] if len(l) > indent_level else "\n"
            for l in lines_we_need
        ]
        # All lines with text have the given indent level or more, so they are not an issue
        # Blank lines, however, can be zero length, hence the exception.
        return "".join(lines)

    def set_section_from_raw_text(self, raw_text, path: Tuple[str, ...]) -> Edit:
        new_lines = self._apply_edit_to_lines(
            self._project_raw_text_to_section_as_edit(raw_text, path))
        diff_as_edit = YamlDoc.edit_from_quick_diff(self.raw_lines, new_lines)
        self.set_raw_text("".join(new_lines))
        return diff_as_edit

    def _project_raw_text_to_section_as_edit(self, raw_text, path: Tuple[str, ...]):
        original_value = self[path]
        raw_text_lines = raw_text.splitlines(keepends=True)
        projected_text_lines = []

        start = EditMark(original_value.start.line, original_value.start.column)
        end = EditMark(original_value.end.line, original_value.end.column)

        # Exception we make when going from block back to null style
        if raw_text == "":
            if (isinstance(original_value, Ydict) and not original_value.flow_style) or \
                    (not isinstance(original_value, Ydict) and original_value.style != ""):
                start.column = 0
                return Edit(start, end, raw_text, raw_text_lines)

        sl = original_value.start.line
        if len(self.raw_lines):
            indent_level = len(self.raw_lines[sl]) - len(self.raw_lines[sl].lstrip())
        else:
            indent_level = 0

        if isinstance(original_value, Ydict):  # Currently, sole use case is in steps
            if original_value.flow_style:
                if original_value == {}:
                    indent_level += 2
                    projected_text_lines += ["\n" + " " * indent_level]
                else:
                    raise ImplementationError("Should not be viewing flow style elements")
        else:  # isinstance(original_value, Ystr):  # Expressions and documentation
            if "\n" in raw_text:
                if isinstance(original_value, YNone) or original_value.style == "":
                    indent_level += 2
                    projected_text_lines += [" |-\n" + " " * indent_level]
            else:
                return Edit(start, end, raw_text, raw_text_lines)

        projected_text_lines += [((' '*indent_level) if len(l) > 1 and n > 0 else "") + l
                                 for n, l in enumerate(raw_text_lines)]
        # 1. First line should have no indent - the cursor position takes care of that
        # 2. All lines with text have the given indent level or more, so they are not an issue
        #    Blank lines, however, can be zero length, hence the exception.
        return Edit(start, end, None, projected_text_lines)

    def _apply_edit_to_lines(self, edit: Edit):
        existing_lines = self.raw_lines
        lines_to_insert = edit.text_lines

        if edit.end is None:
            edit.end = edit.start

        if edit.end.line != edit.start.line:
            edit.end.column = 0

        new_lines = existing_lines[:edit.start.line] + \
                    ([existing_lines[edit.start.line][:edit.start.column]] if edit.start.line < len(existing_lines) else []) + \
                    lines_to_insert + \
                    (([existing_lines[edit.end.line][edit.end.column:]] +
                      (existing_lines[edit.end.line + 1:] if edit.end.line + 1 < len(existing_lines) else []))
                     if edit.end.line < len(existing_lines) else [])

        return new_lines

    @staticmethod
    def edit_from_quick_diff(orig_lines, new_lines) -> Edit:
        L0 = len(orig_lines) - 1
        L1 = len(new_lines) - 1

        upper_n = L0
        for n in range(len(orig_lines)):
            if orig_lines[n] != new_lines[n]:
                upper_n = n
                break

        lower_n = 0
        for n in range(len(orig_lines)):
            if orig_lines[L0 - n] != new_lines[L1 - n]:
                lower_n = n
                break

        start = EditMark(upper_n, 0)
        end = EditMark(L0 - lower_n + 1, 0)

        return Edit(start, end, "".join(new_lines[upper_n:(L1 - lower_n + 1)]), [])