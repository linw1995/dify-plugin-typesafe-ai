# TypeSafe AI for Dify

A Dify **Tool** plugin for [TypeSafe AI](https://docs.typesafe.ai/api).
Use **Yes / No** for plain-text binary judgments, or **Evaluate** for multiple
typed questions in a single request to
`POST https://api.typesafe.ai/v1/systemone`.

- `noul`: a yes/no probability.
- `choice`: a selected option, probability distribution, and confidence.
- `score`: a weighted score, level legend, probability distribution, and confidence.

## Install

Package the project using the [Dify Plugin CLI](https://docs.dify.ai/en/develop-plugin/getting-started/cli):

```sh
mkdir -p dist
dify plugin package . -o dist/typesafe.difypkg
```

In Dify, open **Plugins**, choose **Install from local package**, and select the
package. Configure the **TypeSafe API key** in the provider credentials. Validation
performs a small real evaluation and may consume API credits. A self-hosted Dify
instance must permit installation of locally built, unsigned plugins.

Add **TypeSafe AI / Yes / No** or **Evaluate** to a Workflow, Chatflow, or Agent. This is a tool
provider and appears in the tools list, rather than the model provider settings.
The plugin requires the Python 3.12 plugin runtime and outbound HTTPS access to
`api.typesafe.ai`. It requests no Dify reverse-invocation or storage permissions.

## Yes / No: Chatflow without JSON or code

Connect **User Input -> Yes / No -> IF/ELSE -> Answer**.

| Parameter | Configuration |
| --- | --- |
| `state` | Select the current user message from the variable picker. |
| `instructions` | Keep the default to answer the question in the state, or enter a rule such as `Does the user agree to proceed?`. |
| `yes_criteria` | Optional description of an affirmative answer. |
| `no_criteria` | Optional description of a negative answer. |
| `threshold` | Defaults to `0.5`; adjust to control the yes/no decision. |
| `model` | Defaults to `jev-latest`. |

The tool exposes `probability` as **Number** and `decision` as **Boolean**.
Connect `decision is true` to an Answer node containing your affirmative reply
and the ELSE branch to your negative reply. No extraction Code node is needed.
Alternatively, connect the tool directly to an Answer node referencing its `text`
output for the English `Yes` or `No` reply. The complete API response remains in
`json`; `model` and `usage` are also available as custom outputs.

The threshold comparison is inclusive: `probability >= threshold`. Near-threshold
results still produce a binary decision. The tool only receives the supplied
state; conversation history is not included automatically.

## Evaluate inputs

| Parameter | Default | Description |
| --- | --- | --- |
| `state` | Required | Text to evaluate, or serialized JSON. |
| `questions` | Required | A serialized JSON object mapping your IDs to question definitions. |
| `state_format` | `text` | `text` preserves input exactly; `json` decodes a JSON string, object, or array. |
| `model` | `jev-latest` | TypeSafe model ID or alias. |

In an Agent, `state` and `questions` are supplied by the LLM; configure the model
and state format when attaching the tool. In a workflow, supply the state from an
upstream node and enter or generate the questions JSON. To pass an object or array,
serialize it first and choose `json` as the state format. JSON scalars other than
strings are not valid states. There is no automatic JSON detection.

Evaluate retains a string parameter for questions because Dify's documented
`object` and `array` input types are reserved for MCP tools, rather than ordinary
plugin parameters. For single binary judgments, use **Yes / No** to avoid writing
JSON. For dynamic batches, generate JSON in an upstream Template or Code node
and bind its string output to `questions`.

For example, use `The service has been unavailable since this morning.` as the
state and the following questions JSON:

```json
{
  "needs_attention": {
    "type": "noul",
    "instructions": "Does this report require prompt attention?",
    "criteria": {
      "true": "An ongoing incident needs intervention",
      "false": "An informational update needs no action"
    }
  },
  "owner": {
    "type": "choice",
    "instructions": "Which team should investigate?",
    "criteria": {
      "infrastructure": "Availability or deployment problems",
      "accounts": "Access or subscription problems",
      "other": null
    }
  },
  "impact": {
    "type": "score",
    "instructions": "How much does this affect normal operations?",
    "criteria": ["No disruption", "Partial disruption", "Complete disruption"]
  }
}
```

Instructions may also be JSON objects or arrays. `noul` criteria are optional;
`choice` requires a nonempty option map whose values are strings or `null`;
`score` requires at least two ordered strings. Scores use zero-based levels and
can fall between levels. The plugin preserves probabilities and confidence
returned by TypeSafe without inventing a decision threshold.

## Evaluate outputs

The default Dify `json` output contains the complete API response. Three custom
variables are also emitted for downstream nodes:

| Variable | Type | Contents |
| --- | --- | --- |
| `answers` | Object | Answers keyed by the IDs in `questions`. |
| `model` | String | Model that performed the evaluation. |
| `usage` | Object | `input_tokens` and `output_tokens`. |

For conditional routing, use a Code node to select a value from the dynamic
`answers` object, for example `answers["needs_attention"]["noul"]`, then connect
that number to an IF/ELSE node with your chosen threshold. The built-in `text` and
`files` outputs are not populated.

## Upgrading from 0.1.0

Install the 0.1.1 package and refresh the editor. If an existing Evaluate node
still shows `answers` as File, re-add the tool node and rebind downstream inputs
to refresh its schema. `answers` is an object keyed by question IDs; its updated
schema declares the map value types to prevent Dify's schema matcher from
mistaking an unconstrained object for a file.

For a binary Chatflow, replace Evaluate and the extraction Code node with
**Yes / No**, then branch directly on `decision`.

## Errors and retries

Inputs are validated before sending an evaluation. Missing credentials,
authentication failures, malformed responses, timeouts, and API errors fail the
tool invocation, allowing Dify's error handling to take over.

HTTP `429` and `529` responses are retried at most twice with exponential backoff
and jitter. Other statuses and transport failures are not retried automatically:
a failed connection or read may occur after an evaluation has consumed credits.
Each request has a 5-second connection timeout and 20-second network inactivity
timeout; the plugin runtime request timeout is 120 seconds. Upstream error bodies
are omitted because they may contain submitted data.

## Development

```sh
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests use a mocked HTTP transport and the real Dify SDK. They verify requests,
validation, failures, bounded retries, credential checks, plugin registration,
and workflow output variables without API credits or network access.

For [remote debugging](https://docs.dify.ai/en/develop-plugin/dev-guides-and-walkthroughs/tool-plugin),
copy `.env.example` to `.env`, fill in the debug host and key shown by your Dify
instance, and run:

```sh
uv run python -m main
```

The debug key belongs to Dify. Configure the separate TypeSafe API key in the
plugin's provider settings. The packaging ignore file excludes local environment
files, the virtual environment, tests, and previous packages.

## References

- [TypeSafe API reference](https://docs.typesafe.ai/api)
- [Dify plugin development](https://docs.dify.ai/en/develop-plugin/getting-started/getting-started-dify-plugin)
- [Dify tool output variables](https://docs.dify.ai/en/develop-plugin/features-and-specs/plugin-types/tool)

MIT licensed. This community integration is not an official TypeSafe product.
