# Foundry CSV analysis starter

`main.py` runs a fixed LangGraph workflow: `START -> aggregation -> summary -> END`.
There are two independently callable tools:

- `aggregate(csv_path, objective, run_dir)` profiles the CSV, generates `analysis.py`,
  executes it in Foundry Code Interpreter, and saves a validated `aggregation.csv`.
- `summarize(aggregation_path, objective)` reads the saved aggregates and uses its
  dedicated `SUMMARY_PROMPT` to write `report.json` with summary, questions, and insights.

`csv_agent.py` contains only graph wiring and the public `run()` entry point.
`csv_tools.py` contains the tools, prompts, and artifact validation. The graph always
aggregates before summarizing; no supervisor or model-selected tool routing is needed.

## Setup

Use Python 3.10 or later and install the locked dependencies with `uv sync` from this
directory. Copy `.env.example` to `.env` and set:

```env
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_ENDPOINT=https://your-account.openai.azure.com
AZURE_OPENAI_DEPLOYMENT_NAME=your-model-deployment
```

The app authenticates with the API key through `FoundryClient`. No `az login` or
Foundry project endpoint is required. Use a deployment and region that support
Code Interpreter in the Azure OpenAI Responses API. These same settings also
serve the arithmetic and Flask examples.

## Run

```bash
uv run tiny_ex.py

# Or analyze your own CSV:
uv run main.py path/to/data.csv "Compare the most relevant monthly metrics"
```

`tiny_ex.py` creates six synthetic sales rows in a temporary CSV, runs the complete
agent, and prints the saved artifact paths and report. It still needs a configured
Azure OpenAI endpoint, API key, and model deployment; it does not use mock responses.

Use `--output-dir path/to/results` to change where runs are saved. Each run creates
its own directory with `profile.json`, `analysis.py`, `aggregation.csv`, and
`report.json`. The CLI prints these absolute paths and the report as JSON. CSV inputs
are limited to 10 MiB.

Edit `AGGREGATION_PROMPT` and `SUMMARY_PROMPT` in `csv_tools.py` independently.
Code generation receives only schema/profile information. The summary receives all
validated aggregates and the objective, with no raw CSV attachment or execution tools.
The interpreter's own model context can still see any raw values printed by generated code.

Each successful run uses four model requests: profile, generate code, execute, summarize.
Aggregation allows two repair attempts. Uploaded files are cleaned up on success or
failure; model requests use `store=False` and do not maintain response conversations.
The summary never runs after a failed aggregation. `final_answer` remains in the report
for compatibility and contains the dedicated summary directly.

The implementation uses [LangGraph StateGraph](https://reference.langchain.com/python/langgraph/graph/state/StateGraph)
and [Azure OpenAI Responses with Code Interpreter](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses).

Run local contract tests (no Azure requests):

```bash
uv run python -m unittest -v test_csv_agent
```
