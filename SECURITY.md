# Security reporting

This CLI treats source labels and other source text as untrusted data. It performs
no live LLM calls and does not execute workbook macros or recalculate formulas.
Valid JSON and integrity hashes do not authenticate source data or constrain a
future model. See `docs/audit-contract.md` for the intended consumer boundary.

For an ordinary reproducible validation bug, open an issue using synthetic input.
Do not include confidential ledgers, personal data, credentials, or private files.
For a suspected vulnerability, use GitHub private vulnerability reporting if it
is enabled, or a private contact channel already established with the repository
owner. If neither is available, open an issue requesting a private reporting
channel without publishing exploit details or sensitive input.
