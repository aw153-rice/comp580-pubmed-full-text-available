"""Checks for full_text_available and the pubmed-full-text-available task."""

from .checks import result
from .identity import input_problem, output_problem, same_papers, subset_from_rows
from .rows import load_rows


def verify_input(value):
    problem = input_problem(value)
    if problem:
        return result(False, problem[1])
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    problem = input_problem(input_value) or output_problem(output_value)
    if problem:
        return result(False, problem[1])
    kind, payload = load_rows(workspace, input_value.papers)
    if kind != "ok":
        return result(False, payload)
    if not same_papers(output_value.available, subset_from_rows(input_value.papers, payload)):
        return result(False, "output is not the free-full-text subset in availability.json")
    return result(True, "output matches the recorded rows")


def verify_task(arguments, output, reference, workspace):
    problem = input_problem(arguments) or output_problem(output)
    if problem:
        return result(False, problem[1])
    # A tool run never receives the pin. Judge that call from availability.json.
    if reference is not None:
        problem = output_problem(reference)
        if problem:
            return result(False, problem[1])
        if not same_papers(output.available, reference.available):
            return result(False, "output does not match the reference")
    kind, payload = load_rows(workspace, arguments.papers)
    if kind != "ok":
        return result(False, payload)
    if not same_papers(output.available, subset_from_rows(arguments.papers, payload)):
        return result(False, "availability.json does not support the output")
    if reference is None:
        return result(True, "output matches the recorded rows")
    return result(True, "output matches the reference")
