import json


TOOLS = [
    {
        "type": "function",
        "name": "calculate",
        "description": "Perform an arithmetic calculation with two numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide"],
                },
                "first": {"type": "number"},
                "second": {"type": "number"},
            },
            "required": ["operation", "first", "second"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "summary",
        "description": "Summarize the results of the client's aggregates of transactions",
        "parameters": {
            "type": "object",
            "properties": {"results_file_path": {"type": "string"}},
        },
    },
]


def calculate(operation: str, first: float, second: float) -> float:
    if operation == "add":
        return first + second
    if operation == "subtract":
        return first - second
    if operation == "multiply":
        return first * second
    if operation == "divide":
        if second == 0:
            raise ValueError("Cannot divide by zero")
        return first / second

    raise ValueError(f"Unknown operation: {operation}")


def summary(results_file_path: str):
    with open(results_file_path, "r") as file:
        return file.read()


def execute_tool(name: str, arguments: str) -> str:
    if name == "calculate":
        result = calculate(**json.loads(arguments))
        return str(result)
    if name == "summary":
        result = summary(**json.loads(arguments))
        return result

    raise ValueError(f"Unknown tool: {name}")
