# Foundry CSV analysis starter

`CsvAnalysisAgent.run(csv_path, objective, output_dir)` uses a LangGraph loop:

```text
START → write_python_code(prompt) → execute_python_code(code_id)
                                   ↳ success → summarize → END
                                   ↳ error → write with diagnostics (up to 2 repairs)
```

The write tool makes a dedicated Azure OpenAI Foundry Responses call, validates the
returned Python, and saves it under `programs/<code_id>.py`. It returns `code_id`,
`code`, and `script_path`. The execute tool runs that saved file with the local
Python interpreter. It returns the exit code, stdout, stderr, and files generated
in that execution's artifact directory. The script reads `CSV_INPUT_PATH` and
writes `AGGREGATION_OUTPUT_PATH`. A run succeeds only after the resulting
`aggregation.csv` passes validation; the summary model then sees only aggregate
names and numeric values. The summary call uses Pydantic structured output and saves
an `items` list. Each item has string `Question`, `Insight`, and
`Signal_in_the_data` fields.

Each run saves `profile.json`, all generated programs, execution artifacts,
`aggregation.csv`, and `report.json` in a unique output directory. Failed runs
do not create a report. Execution has a 60 second timeout, and at most three
programs are generated. Generated code runs on the current computer with the
current user's filesystem access, so use this workflow only with a trusted
Foundry deployment and suitable local environment.

## Setup

From `starter`, install the dependencies in `pyproject.toml` and set these in
`.env`:

```env
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_ENDPOINT=https://your-account.openai.azure.com
AZURE_OPENAI_DEPLOYMENT_NAME=your-model-deployment
```

Run:

```bash
uv run main.py path/to/data.csv "Compare monthly revenue"
uv run tiny_ex.py
uv run python -m unittest -v test_csv_agent
```

The tests use a fake Foundry response and execute generated Python locally.
They do not make Azure requests.
