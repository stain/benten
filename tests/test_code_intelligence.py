#  Copyright (c) 2019 Seven Bridges. See LICENSE

import pathlib

from lib import load, load_type_dicts

from benten.langserver.lspobjects import Position, Location


current_path = pathlib.Path(__file__).parent
schema_path = pathlib.Path(current_path, "../benten/000.package.data/")


type_dicts=load_type_dicts()
path = current_path / "cwl" / "ebi" / "workflows" / "cmsearch-multimodel-wf.cwl"


def test_definition():
    doc = load(doc_path=path, type_dicts=type_dicts)
    linked_uri = pathlib.Path(current_path / "cwl" / "ebi" / "utils" / "concatenate.cwl")
    doc_def_loc = doc.definition(loc=Position(50, 20))
    assert isinstance(doc_def_loc, Location)
    assert doc_def_loc.uri == linked_uri.as_uri()


def test_record_field_completion():
    doc = load(doc_path=path, type_dicts=type_dicts)
    cmpl = doc.completion(Position(7, 0))
    assert "doc" in [c.label for c in cmpl]


def test_type_completion():
    doc = load(doc_path=path, type_dicts=type_dicts)
    cmpl = doc.completion(Position(14, 11))
    assert "string" in [c.label for c in cmpl]


def test_step_input_completion():
    doc = load(doc_path=path, type_dicts=type_dicts)
    cmpl = doc.completion(Position(37, 38))
    assert "covariance_models" in [c.label for c in cmpl]


def test_requirement_completion():
    doc = load(doc_path=path, type_dicts=type_dicts)
    cmpl = doc.completion(Position(8, 16))
    assert "InlineJavascriptRequirement" in [c.label for c in cmpl]


def test_requirement_sub_completion():
    this_path = current_path / "cwl" / "ebi" / "workflows" / "InterProScan-v5-chunked-wf.cwl"
    doc = load(doc_path=this_path, type_dicts=type_dicts)
    cmpl = doc.completion(Position(8, 10))
    assert "InlineJavascriptRequirement" in [c.label for c in cmpl]


def test_missing_name_space():
    this_path = current_path / "cwl" / "misc" / "cl-missing-namespace.cwl"
    doc = load(doc_path=this_path, type_dicts=type_dicts)
    assert len(doc.problems) == 1
    namespace_problem = next(p for p in doc.problems if p.range.start.line == 15)
    assert namespace_problem.message.startswith("Expecting one of")


def test_unused_input():
    this_path = current_path / "cwl" / "misc" / "wf-unused-input.cwl"
    doc = load(doc_path=this_path, type_dicts=type_dicts)
    assert len(doc.problems) == 1
    namespace_problem = next(p for p in doc.problems if p.range.start.line == 4)
    assert namespace_problem.message.startswith("Unused input")


def test_implicit_inputs():
    this_path = current_path / "cwl" / "misc" / "wf-when-input.cwl"
    doc = load(doc_path=this_path, type_dicts=type_dicts)
    assert len(doc.problems) == 0

    cmpl = doc.completion(Position(12, 8))
    assert "new_input" in [c.label for c in cmpl]


def test_invalid_input():
    this_path = current_path / "cwl" / "misc" / "wf-invalid-input.cwl"
    doc = load(doc_path=this_path, type_dicts=type_dicts)
    assert len(doc.problems) == 1


def test_port_completer():
    this_path = current_path / "cwl" / "misc" / "wf-port-completer.cwl"
    doc = load(doc_path=this_path, type_dicts=type_dicts)

    cmpl = doc.completion(Position(10, 14))  # Not a list
    assert "in1" in [c.label for c in cmpl]

    cmpl = doc.completion(Position(23, 11))  # Is a list
    assert "out1" in [c.label for c in cmpl]

    cmpl = doc.completion(Position(24, 9))  # Is a list
    assert "in1" in [c.label for c in cmpl]
