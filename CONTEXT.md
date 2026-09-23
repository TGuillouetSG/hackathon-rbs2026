# CSV Analysis

This context describes analysis of a source dataset through precomputed metrics and their interpretation.

## Language

**Source dataset**:
The records supplied for analysis in a CSV file.

**Aggregation file**:
The saved collection of computed metrics of interest from the source dataset.
_Avoid_: Summary, report

**Insight**:
An interpretation supported by values in the aggregation file.
_Avoid_: Metric

**Metric selection**:
The list of exact aggregate names identifying which precomputed results in an aggregation file are included in an analysis.
_Avoid_: Metric calculation

**Aggregate name**:
The unique identifier of one computed result in an aggregation file. Each grouped result has its own name, such as `revenue_2026_01`.

**Analysis report**:
A summary, questions, and insights based on the selected precomputed metrics in an aggregation file.
_Avoid_: Aggregation file

**Supervisor guidelines**:
The rules that govern the choice of metrics of interest for a source dataset.

**Dataset profile**:
The source dataset's column names, inferred types, and data-quality counts, without raw records.
