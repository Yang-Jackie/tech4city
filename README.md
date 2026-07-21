# tech4city

## Backend

The backend design is documented in [`ARCHITECTURE.md`](ARCHITECTURE.md), with setup and
operational instructions in [`backend/README.md`](backend/README.md). Offline mode remains
lightweight; MongoDB and the local model stack are explicit optional configurations.

## Run Preprocessing

```sh
python -m utils.preprocess_confessit --input_file data/nusconfessit.json --output_file data/nus_processed.json
python -m utils.preprocess_confessit --input_file data/ntuconfessit.json --output_file data/ntu_processed.json
```

## Test TDLib

See [README-TDLIB.md](README-TDLIB.md) for the official-source TDLib build and interactive
Python user-account smoke tests. Run `python -m telegram.bridge` to stream new Telegram text
messages into the backend; the TDLib guide documents the local two-process workflow.
