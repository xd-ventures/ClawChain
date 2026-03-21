def load_bot_pool(file_path: str) -> list[tuple[str, str]]:
    """Load bot pool from text file.

    Format: one line per bot, 'bot_name:bot_token'.
    Skips blank lines and lines starting with #.
    Returns list of (bot_name, bot_token) tuples.
    """
    bots = []
    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, token = line.split(":", 1)
            bots.append((name.strip(), token.strip()))
    return bots
