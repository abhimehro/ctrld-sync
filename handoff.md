===== ELIR =====
PURPOSE: Extracted `get_default_config`, `validate_config`, and `load_config` into a dedicated `config.py` module to reduce `main.py` monolithic footprint.
SECURITY: No behavioral changes, standard filesystem operations were preserved exactly as they were in `main.py`.
FAILS IF: An upstream circular dependency arises if shared constants aren't managed properly (they are currently imported inline in config.py functions, breaking the loop).
VERIFY: `uv run python main.py --help` behavior remains unchanged; all 174 tests pass.
MAINTAIN: If `constants.py` is introduced in the future, `DEFAULT_FOLDER_URLS`, `BATCH_SIZE`, and `MAX_RETRIES` should be moved there instead of inline importing them inside config functions.
