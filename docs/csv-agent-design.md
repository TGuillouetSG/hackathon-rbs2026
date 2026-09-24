# CSV analysis agent

`starter/csv_agent.py` builds a LangGraph workflow with explicit
`write → execute → inspect` steps. A failed program or invalid aggregation
routes back to `write` with the previous source and bounded diagnostics.
The loop permits two repairs after the first attempt. Successful execution
routes to `summary`; exhausted attempts raise an error.

`starter/csv_tools.py` provides the two code tools:

- `write_python_code(prompt)` makes a dedicated Foundry Responses call,
  checks syntax and size, saves source in `programs/<code_id>.py`, and returns
  the ID and source.
- `execute_python_code(code_id)` accepts only IDs saved for that run, starts
  the saved file with the local Python interpreter, and returns stdout, stderr,
  exit status, and generated file paths. A timeout or invalid
  `aggregation.csv` is a repairable failure.

The CSV profile is computed locally and contains only column names, inferred
numeric versus string types, missing counts, and row count. The final summary
request receives only validated aggregate names and values and uses Foundry's
Pydantic structured output for an `items` list of `Question`, `Insight`, and
`Signal_in_the_data` strings. Generated code
has the local user's filesystem access. The subprocess has a 60 second
timeout and omits Azure/OpenAI credential variables from its environment;
it is not a security sandbox.

The public `run(csv_path, objective, output_dir)` method returns artifact
paths, the successful code ID, execution result, and report. The CLI and
`tiny_ex.py` use this entry point.
