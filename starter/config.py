from pathlib import Path

from dynaconf import Dynaconf

STARTER_DIR = Path(__file__).resolve().parent

settings = Dynaconf(
    envvar_prefix="DYNACONF",
    settings_files=[STARTER_DIR / "settings.toml", STARTER_DIR / ".secrets.toml"],
)

# `envvar_prefix` = export envvars with `export DYNACONF_FOO=bar`.
# `settings_files` = Load these files in the order.
