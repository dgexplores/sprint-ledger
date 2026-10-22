# Demonstrate and explain this project

1. Open the demo. Load the fictional example and Find commitments using offline mode. Four action proposals should appear with source lines.
2. Inspect titles, owners and dates; complete missing priority/criteria manually. Unknown fields must not be invented.
3. Approve the reviewed tasks. Then create local issues. Nothing is sent to Jira in this flow.
4. Explain why repeated local publishing cannot create duplicate issues and why approval is separate from extraction.
5. Optional unstructured extraction requires a compatible provider and AI operator token. Optional Jira export additionally needs server-side Jira configuration, explicit confirmation and a separate publish token.

Explain: validated proposals, approval state, durable pre-POST intent, replay protection and why a timeout is an uncertain result rather than permission to retry blindly. A configured real Jira tenant has not been tested by the build process.
