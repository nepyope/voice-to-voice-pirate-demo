# Connect the Captain to Reachy Mini

This package uses the existing Reachy Mini conversation app as its audio client.
Connection keys and native profile parsing were checked against app commit
`b9f58a3587d79a3275d4402d1a8d210649d62d50`. A physical robot was not available.

## Expose the backend

On the GPU host, add `compose.reachy.yaml` to whichever inference mode you use.
For local inference:

```bash
python3 scripts/preflight.py --mode local --reachy
docker compose -f compose.yaml -f compose.reachy.yaml up -d --build
```

For both vLLM services:

```bash
docker compose -f compose.yaml -f compose.vllm.yaml -f compose.llm-vllm.yaml -f compose.reachy.yaml up -d --build
```

The overlay publishes `127.0.0.1:8765` by default. From the machine running the
conversation app, create a forward tunnel to the GPU host:

```bash
ssh -N -L 8765:127.0.0.1:8765 YOUR_USER@YOUR_GPU_HOST
```

Then that client's endpoint is `ws://127.0.0.1:8765/v1/realtime`. If the app runs
on the robot and you initiate SSH from the GPU host instead, reverse the tunnel:

```bash
ssh -N -R 8765:127.0.0.1:8765 ROBOT_USER@ROBOT_HOST
```

Alternatively, set `REALTIME_BIND` in the GPU demo's `.env` to its trusted LAN IP
and use that address in the client URL. Plain WebSocket is suitable only for the
trusted local/tunnel arrangement; this overlay does not add authentication.

## Load the Captain personality

With the robot daemon and conversation app installed, copy this folder to the
machine that runs the conversation app. Add the entries in `reachy.env.example`
to **that app's** `.env`, setting the profiles directory to its actual absolute
path. Do not overwrite an existing app `.env` wholesale. The example chooses
local connection mode and the Captain profile.

Start the conversation app:

```bash
reachy-mini-conversation-app --no-camera
```

If using its UI, select the Captain personality and the local connection in
Settings. Saved UI selections can override the environment's profile fallback.
Its UI also uses port 7860 by default; use the console client or a separate
machine if the demo UI already occupies that port.

The profile has an empty `default_tools` list. Reset any saved per-profile tool
override before an audio-only run. It uses the same language-following prompt as
the browser. The speaker is selected by `VOICE` on the GPU server. Reachy's UI
still lists Qwen speakers; the patched remote handler retains the configured
clone instead of forwarding an unrelated client preset. Local OmniVoice already
uses its configured clone. The app may send its normal startup greeting; test
language switching on subsequent spoken turns.

## Verify the connection

From the client machine, using this demo's Python test dependencies:

```bash
python scripts/smoke_realtime.py --url ws://127.0.0.1:8765/v1/realtime \
  --text "Captain, tell me where our next adventure will take us." \
  --output artifacts/reachy-endpoint.wav
```

This tests the robot-facing endpoint, not the robot's microphone or speaker.
Then start the actual app and run the listening checks in `VALIDATION.md`:
English → French → German, interrupt a reply, disconnect and reconnect. Record
speaker quality and playback behavior. The browser and robot share the same
single pipeline unless `NUM_PIPELINES` is increased; stop one before starting
the other. Robot movement and tool calling have not been implemented or tested.

Sources: [conversation app](https://github.com/pollen-robotics/reachy_mini_conversation_app),
[profile parser at the checked revision](https://github.com/pollen-robotics/reachy_mini_conversation_app/blob/b9f58a3587d79a3275d4402d1a8d210649d62d50/src/reachy_mini_conversation_app/profile_store.py),
[HF local Reachy guide](https://huggingface.co/blog/local-reachy-mini-conversation).
