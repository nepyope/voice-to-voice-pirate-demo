# Painty UI server

Start from the [project README](../README.md). The complete stack uses Compose.

For UI-only development, install `requirements.txt`, run `npm ci`, and start
`uvicorn server:app --host 127.0.0.1 --port 7860` from this directory.
Set `SPEECH_TO_SPEECH_URL=ws://127.0.0.1:8765/v1/realtime` to point the server
at your running backend. It is a server-side address; the browser connects to
the same-origin `/api/realtime` relay. WebRTC is not offered in this package.

`npm test` runs the JavaScript checks. Python integration checks live in the
parent `tests/` directory. `DESIGN.md` describes the retained UI conventions.
