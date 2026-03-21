import pytest
from orchestrator.bot_pool import load_bot_pool


def test_parse_valid_file(bot_pool_file):
    bots = load_bot_pool(bot_pool_file)
    assert len(bots) == 3
    assert bots[0] == ("alpha_bot", "111111111:AAA-token-alpha")
    assert bots[1] == ("beta_bot", "222222222:AAA-token-beta")


def test_skip_comments_and_blanks(tmp_path):
    f = tmp_path / "bots.txt"
    f.write_text("# comment\n\n  \nbot1:tok1\n# another\nbot2:tok2\n")
    bots = load_bot_pool(str(f))
    assert len(bots) == 2


def test_whitespace_trimming(tmp_path):
    f = tmp_path / "bots.txt"
    f.write_text("  my_bot  :  my_token  \n")
    bots = load_bot_pool(str(f))
    assert bots[0] == ("my_bot", "my_token")


def test_token_with_colons(tmp_path):
    """Telegram tokens have format 123456:ABC-xyz — colon in value."""
    f = tmp_path / "bots.txt"
    f.write_text("mybot:123456789:AAHfGz_secret\n")
    bots = load_bot_pool(str(f))
    assert bots[0] == ("mybot", "123456789:AAHfGz_secret")


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        load_bot_pool("/nonexistent/bots.txt")
