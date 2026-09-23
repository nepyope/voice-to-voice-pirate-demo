# Source notices

The original UI and reference documents were supplied in the user attachment.
Their authors and original links are retained. Do not infer a new blanket license
for material that lacked a license in that archive.

Backend patches and test fixtures target huggingface/speech-to-speech commit
`ca5c33c9bb5e381288d315d1f8da122613845c4c` (Apache-2.0).
The corresponding license is in `tests/fixtures/upstream/LICENSE`.

OmniVoice code is Apache-2.0; model weights have separate terms, including the
CC-BY-NC restriction stated in the supplied model documentation. Check the model
card before commercial use. No model weights are bundled.

This completion retains the supplied Painty the Pirate recordings and dub
transcripts only in the complete project bundle; no redistribution permission
is asserted by their inclusion. `scripts/package_demo.py --public` excludes
those assets and includes only the original OmniVoice-designed Captain reference
already present in the handoff. That reference's original generation metadata
is retained under `voices/captain/`. It was not regenerated in this pass.

The OmniVoice model card identifies its pretrained weights as CC-BY-NC. Selecting
an original reference voice does not alter those model terms:
https://huggingface.co/k2-fsa/OmniVoice#license
