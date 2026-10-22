# Sprint Ledger: upstream project study

Sprint planning through Copilot Studio and MCP integrations.

**Deepak Gangwar’s documentation for a local study copy of [SprintForge](https://github.com/Shrusti13/sprint-forge).** The portfolio display name has changed; the upstream implementation and authorship have not. Original authors: Shrushti Shah and Bhushan Gawale.

## At a glance

| Item | Status |
|---|---|
| Purpose | Architecture study and preparation for an attributed extension |
| Current work in this copy | Portfolio naming and recruiter-oriented documentation, prepared with AI assistance; no upstream application-code changes |
| Application code changes | None |
| Runtime verification | Not performed for this clone |
| Hosted demo | No deployment of this clone; previous similarly named demos are separate implementations |
| Upstream snapshot | `8977eebbb69a1e98747158f50a01eb8ab407a58b` |

## Problem and approach

Planning conversations need to become structured tasks with useful references before a team can execute them.

```text
Planning email → Copilot Studio extraction → Microsoft Learn MCP enrichment → sprint-plan JSON → Jira MCP issue creation
```

**Technology:** Microsoft Copilot Studio, Microsoft Learn MCP, Jira MCP, Power Platform and Jira Cloud.

## Explore the repository

| Path | What to inspect |
|---|---|
| [solution/SprintForge_1_0_0_1_managed.zip](https://github.com/Shrusti13/sprint-forge/blob/8977eebbb69a1e98747158f50a01eb8ab407a58b/solution/SprintForge_1_0_0_1_managed.zip) | Upstream managed Power Platform solution |
| [solution/ArchitectureOverview.png](https://github.com/Shrusti13/sprint-forge/blob/8977eebbb69a1e98747158f50a01eb8ab407a58b/solution/ArchitectureOverview.png) | Upstream architecture diagram |
| [demo](https://github.com/Shrusti13/sprint-forge/tree/8977eebbb69a1e98747158f50a01eb8ab407a58b/demo) | Upstream demonstration materials |

## Setup and demonstration status

Use a Power Platform environment with Copilot Studio access. Import the managed solution using Power Apps Solutions, then configure the required connection references, email integration, Microsoft Learn MCP and Jira MCP credentials in that environment. Importing the package alone does not configure those services. No solution import or external issue creation was performed here.

## What I can discuss with a recruiter

**Relevant areas:** Structured extraction, agent workflows, REST-backed integrations, MCP, documentation grounding and workflow validation; the upstream solution is not a Python backend.

Explain how the plan is structured, how references support acceptance criteria, and how you would add approval, duplicate prevention and recovery after partial Jira failures.

An accurate introduction is: “I am studying SprintForge under the working portfolio name Sprint Ledger. I have organized its documentation; the implementation is upstream. I will identify and demonstrate my own engineering changes separately as they are completed.”

## Scope and evidence

The upstream README describes optional attachment processing as future work in its demo section; it must not be advertised as verified functionality. The upstream sprint-preparation time saving has not been reproduced here. This clone is separate from the deployed Python Sprint Ledger demo, which creates local issues.

Renaming and README editing do not establish implementation experience, benchmark results or a working deployment. Upstream awards belong to the original team. This upstream copy should be described as a study copy until substantive changes are implemented and verified. The separate application in this repository has its own implementation and verification record in the root README.

## Attribution and reuse

Original source: [SprintForge](https://github.com/Shrusti13/sprint-forge). Original authors: Shrushti Shah and Bhushan Gawale. Upstream authorship and applicable notices are recorded here; the upstream source is not included in this repository.

No clear reuse licence was found in the inspected files. This is a local reference copy; public redistribution needs appropriate permission.

[Original upstream README](https://github.com/Shrusti13/sprint-forge/blob/8977eebbb69a1e98747158f50a01eb8ab407a58b/readme.md).

## Relationship to this repository

This document describes the original upstream reference, not the application deployed from this repository. Only study documentation is published here; the upstream source is not included in this repository. Use the [repository README](../README.md) for the current application, live demo, tests and contribution details.
