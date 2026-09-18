# Privacy

This plugin sends the state, question definitions, selected model, and API key to
`https://api.typesafe.ai/v1/systemone` over HTTPS. The API key is sent as a Bearer
credential. Credential validation sends a fixed connection-check prompt and may
consume API credits.

The plugin does not persist inputs, answers, or credentials, and does not add
analytics or telemetry. Dify manages provider credentials and may retain tool
inputs and outputs according to the workspace's settings. TypeSafe processes
submitted data under its own terms and privacy policy; review these before
submitting sensitive information.

Errors do not include upstream response bodies or transport exception details.
