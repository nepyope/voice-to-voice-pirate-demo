# Captain implementation context

The active demo is specified in the project README and `pirate.json`.
It uses Parakeet TDT v3, local Qwen3-4B by default, and OmniVoice with a persistent
reference voice. The optional vLLM service shares the same reference.
`/api/realtime` proxies the fixed server-side backend address. Camera input and
WebRTC are not offered; no robot movement tools are installed. See REPORT.md for
what was tested and what still needs hardware validation.
