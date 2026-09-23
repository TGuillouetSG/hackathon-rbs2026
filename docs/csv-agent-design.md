# CSV analysis agent

The workflow is a compiled LangGraph `StateGraph` with two nodes:

```text
START -> aggregation -> summary -> END
```

`starter/csv_agent.py` defines the state, wraps the two operations as LangChain
`StructuredTool` instances, and connects them in order. `run(csv_path, objective,
output_dir)` preserves the CLI contract and creates a unique artifact directory.
There is no supervisor, metric-selection function call, or final rewriting request.

## Aggregation tool

`aggregate(csv_path, objective, run_dir)` in `starter/csv_tools.py` owns the full
computation lifecycle:

1. Validate and upload the source CSV (maximum 10 MiB).
2. Profile schema and missing counts using Foundry Code Interpreter; save `profile.json`.
3. Generate Python from that profile and `AGGREGATION_PROMPT`; save `analysis.py`.
4. Upload and execute the script in Foundry Code Interpreter.
5. Download `aggregation.csv` and validate its exact `aggregate_name,value` header,
   unique names, finite numeric values, maximum 1,000 rows, and maximum 1 MiB size.
6. Return the local script and aggregation paths; clean up uploaded files in `finally`.

Generation or output-validation failures allow two repair attempts. API failures
propagate. No generated Python is executed on the application host. The summary node
is reached only after aggregation succeeds.

## Summary tool

`summarize(aggregation_path, objective)` independently reads and validates the saved
CSV, then calls the model with `SUMMARY_PROMPT`. Its only dataset input is the saved
aggregate names and values. It has no Code Interpreter or raw CSV attachment.

The report contains a summary, questions, insights, and the aggregate values used.
The legacy `selected_aggregates` key now includes all saved metrics. The legacy
`final_answer` key is the summary, with no extra rewriting call. The tool validates
the report structure, saves `report.json` beside the CSV, and returns its path and data.

## Operational behavior

A successful run uses four model requests. Each request is independent and uses
`store=False`; response conversation tracking and deletion are unnecessary. Credentials
remain in the existing `FoundryClient` configuration. Uploaded CSV and script files
are deleted after aggregation, including on failure. Cleanup failures are logged.

Code generation receives schema/profile data only. Interpreter profiling and execution
still rely on prompts to avoid printing raw records; this is not strict raw-data isolation.
The summary prompt treats aggregate names as data and requires evidence-grounded claims.

## Validation

Local fake-client tests exercise the real compiled graph, artifact saving, prompt and
input separation, cleanup, bounded repair, and failure propagation. Live Azure execution
requires a deployment supporting Code Interpreter and is not covered by these tests.
