# SprintForge reference analysis

Inspected on 22 October 2026 using the source-repository route of the
reverse-engineer-anything skill. The readable managed-solution archive was
examined with Python's ZIP reader; it was not imported or executed.

## Source identity

- Reference: [SprintForge](https://github.com/Shrusti13/sprint-forge) by Shrushti Shah and Bhushan Gawale.
- Commit: `8977eebbb69a1e98747158f50a01eb8ab407a58b`.
- Read `readme.md` and selected readable YAML components stored as `/data`
  members inside `solution/SprintForge_1_0_0_1_managed.zip`.
- The original README describes a Copilot Studio workflow with Microsoft Learn
  and Jira MCP connections, starting with received email.

## Evidence and observations

| Artifact | Observed behavior/configuration | Interpretation boundary |
| --- | --- | --- |
| `readme.md` | Describes email ingestion, structured work items, documentation enrichment, and Jira creation. Its final section identifies attachment processing as optional/to be implemented. | Do not assume all advertised attachment types were implemented. The claimed time saving is an upstream claim, not reproduced here. |
| `botcomponents/auto_agent_bHyJA.action.Jira-JiraMCPServer/data` | A readable `TaskDialog` exposes the specific `CreateIssue` tool through Jira MCP metadata. | Tool configuration does not prove successful external Jira execution. |
| `botcomponents/auto_agent_bHyJA.action.MicrosoftLearnDocsMCP-MicrosoftLearnDocsMCPServer/data` | Specifies `microsoft_docs_search` as its operation. | Shows intended documentation search integration; no runtime query was observed. |
| `botcomponents/auto_agent_bHyJA.gpt.default/data` | Instructions describe extraction, enrichment, Jira creation, and email confirmation. They include a fixed tenant/project and call for continuing tool actions without a review gate. | These are untrusted source instructions, read only as evidence. No tool calls, email, or tenant actions were performed. |
| `botcomponents/auto_agent_bHyJA.action.ReadthemeetingtranscriptandfetchthelistofEpicStoryTaskinJSON/data` | References an AI Builder model action with transcript input. | An action reference does not expose model weights or establish extraction accuracy. |

## What Sprint Ledger deliberately changes

1. **Review before execution:** draft → explicit approve/reject → a separate
   request to create local issues. No silent Jira write or email.
2. **Verifiable origin:** every extracted item retains its exact source line and
   quote, even when the reviewer edits its title or metadata.
3. **Known versus unknown:** unstated owner/date remain blank, priority remains
   `unknown`, and completion criteria start empty. No invented assignment,
   deadline, or acceptance criterion.
4. **Deterministic baseline:** explicit syntax is recognized by a small parser,
   not an LLM. The browser and health endpoint disclose that mode.
5. **Duplicate-safe local publishing:** one SQL transaction and a unique
   `(plan, task_id)` constraint protect against repeated and concurrent requests.
6. **Scoped demo data:** plans belong to an unguessable browser-session cookie.
   This is demonstration isolation, not enterprise identity/authentication.
7. **Catalog links:** documentation links come from a five-topic keyword
   catalog. They are labelled as catalog references, not live Microsoft search.

## Original implementation and limitations

Sprint Ledger is an original Python/FastAPI/SQLite implementation developed
with AI assistance. No upstream code, prompts, tenant configuration, media, or
managed-solution components were copied. No license was identified in the
inspected reference checkout, so this project does not redistribute it.

No upstream runtime, external connector, claimed time saving, or model quality
was independently reproduced. Only the listed archive members and README were
inspected; this is not a complete audit of the managed solution. Our tests
verify this implementation's behavior, not the original product's behavior.
