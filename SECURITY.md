# Security

Supported development version: the current `main` branch and the latest published release, when a release exists.

Do not include API keys, authentication headers, company designs, or unredacted model responses in an Issue or log attachment. If a key has been exposed, revoke it at the provider before reporting the problem.

Use the repository's **Security → Report a vulnerability** flow if private vulnerability reporting is enabled. Otherwise, contact the repository owner privately through an existing trusted channel. Avoid creating a public Issue containing exploit details or confidential data.

The Web app sends API requests from the browser to the endpoint selected by the user. The local MCP optional provider sends requests from the local process. Installing an MCP server permits the host to invoke its advertised tools; review the installation source and client configuration. The server's artifact output is restricted to its configured workspace.

We aim to acknowledge reports and coordinate a fix before disclosure. This document does not promise a response deadline or a security certification.
