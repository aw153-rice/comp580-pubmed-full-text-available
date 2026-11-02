"""The deterministic verifier: each tool's checks live in its own module, on contract instances."""

from contract import Task, Tool

from . import full_text, pin

TOOLS = {
    Tool.FULL_TEXT_AVAILABLE: full_text,
    Tool.PIN_FULL_TEXT: pin,
}
TASKS = {Task.PUBMED_FULL_TEXT_AVAILABLE: full_text.verify_task}


def verify_input(tool, value):
    return TOOLS[Tool(tool)].verify_input(value)


def verify_output(tool, input_value, output_value, workspace):
    return TOOLS[Tool(tool)].verify_output(input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
