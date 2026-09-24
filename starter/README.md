# Foundry CSV analysis starter

`CsvAnalysisAgent.run(csv_path, objective, output_dir)` uses a single-pass LangGraph workflow:

```text
START → write_python_code(prompt) → execute_python_code(code_id)
                                   ↳ success → summarize → END
                                   ↳ error → fail with diagnostics
```

The write tool makes a dedicated Azure OpenAI Foundry Responses call, validates the
returned Python, and saves it under `programs/<code_id>.py`. It returns `code_id`,
`code`, and `script_path`. The execute tool runs that saved file with the local
Python interpreter. It returns the exit code, stdout, stderr, and files generated
in that execution's artifact directory. The script reads `CSV_INPUT_PATH` and
writes `AGGREGATION_OUTPUT_PATH`. A run succeeds only after the resulting
`aggregation.csv` passes validation; the summary model then sees only aggregate
names and numeric values. The summary call uses Pydantic structured output and saves
an `items` list. Each item has string `Insight`, `signal_in_the_data`, and
`details` fields, plus a nonempty `questions` list for the advisor.

Each run saves `profile.json`, all generated programs, execution artifacts,
`aggregation.csv`, and `report.json` in a unique output directory. Failed runs
do not create a report. Execution has a 60 second timeout. Code generation is
limited to one request, a 30 second request timeout, and 2500 output tokens;
SDK retries are disabled. A slow or invalid response fails the run. Generated code runs on the current computer with the
current user's filesystem access, so use this workflow only with a trusted
Foundry deployment and suitable local environment.
The generation request uses low reasoning effort to reduce first-run latency;
the selected code deployment must support that setting.

Every run makes a fresh code-generation request. Results include
`generation_seconds` so first-run and repeated-run latency can be measured.
Set `AZURE_OPENAI_CODE_DEPLOYMENT_NAME` to a faster code-capable deployment to
speed up code generation; the summary still uses `AZURE_OPENAI_DEPLOYMENT_NAME`.

## Setup

From `starter`, install the dependencies in `pyproject.toml` and set these in
`.env`:

```env
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_ENDPOINT=https://your-account.openai.azure.com
AZURE_OPENAI_DEPLOYMENT_NAME=your-model-deployment
AZURE_OPENAI_CODE_DEPLOYMENT_NAME=optional-faster-code-deployment
```

Run:

```bash
uv run main.py path/to/data.csv "Compare monthly revenue"
uv run tiny_ex.py
uv run python -m unittest -v test_csv_agent
```

## Appointment page

The demo has two synthetic customers configured in `data/customers.json`:
Annie (`annie`, the default) and Marc (`marc`). Use the visible switcher on `/`,
or open `/?customer=marc` and `/rdv?customer=marc` directly. Unknown customer IDs
return 404. Both pages and the RDV workflow use the same selected customer.

Annie's missing-contact scenario uses `inputs/client-002.csv`, the same file as
`tiny_ex.py`; Marc's possible property-purchase scenario uses
`data/marc_account_operations.csv`.
The page at `/rdv` automatically calls `CsvAnalysisAgent.run` through
`POST /api/rdv/workflow?customer=<id>` with the same objective as `tiny_ex.py`
and displays its full structured report. Each card shows an insight, its data
signal, and suggested questions. The meeting outline includes those questions.
The profile-based brief remains visible if analysis fails. Agent artifacts are
saved under `starter/output/rdv/<id>/` in unique per-run subdirectories.
When the agent returns no complete topic, the page displays an empty-state
warning. If analysis fails, the page displays an error instead of demo topics.

Start the Flask app from `starter` with `uv run flask --app server.app run`.
Starting from `starter/server` with `python -m flask --app app run` also works.
The Azure Foundry settings listed above are required for the CSV analysis.

The tests use a fake Foundry response and execute generated Python locally.
They do not make Azure requests.
