import getpass
import os

from studip_sync import get_config_file
from studip_sync.arg_parser import ARGS
from studip_sync.config_creator import ConfigCreator
from studip_sync.constants import URL_BASEURL_DEFAULT
from studip_sync.helpers import JSONConfig, ConfigError


class Config(JSONConfig):

    def __init__(self):
        self.args = ARGS

        config_path = get_config_file()

        self.config_dir = os.path.dirname(config_path)

        self._username = None
        self._password = None

        super(Config, self).__init__(config_path)

    def _check(self):
        if not self.files_destination and not self.media_destination:
            raise ConfigError("Both target directories are missing. You can specify the target directories "
                              "via the commandline or the JSON config file!")

        if not self.username:
            raise ConfigError("Username is missing")

        if not self.password:
            raise ConfigError("Password is missing")

    @property
    def last_sync(self):
        if not self.config:
            return 0

        last_sync = self.config.get("last_sync")
        if last_sync:
            return last_sync
        else:
            return 0

    def update_last_sync(self, last_sync):
        if not self.config:
            return

        new_config = self.config
        new_config["last_sync"] = last_sync
        ConfigCreator.replace_config(new_config)

    @property
    def plugins(self):
        if not self.config:
            return []

        return self.config.get("plugins", [])

    def update_plugins(self, plugins):
        if not self.config:
            return

        new_config = self.config
        new_config["plugins"] = plugins
        ConfigCreator.replace_config(new_config)

    def user_property(self, prop):
        if not self.config:
            return None

        user = self.config.get("user")

        if not user:
            return None

        return user.get(prop)

    @property
    def username(self):
        if self._username:
            return self._username

        self._username = self.user_property("login") or input("Username: ")
        return self._username


    @property
    def password(self):
        if self._password:
            return self._password

        self._password = self.user_property("password") or getpass.getpass()
        return self._password

    @property
    def base_url(self):
        if not self.config:
            return URL_BASEURL_DEFAULT

        return self.config.get("base_url", URL_BASEURL_DEFAULT)


    @property
    def files_destination(self):
        if not self.args.destination == None:
            files_destination = self.args.destination
        else:
            if not self.config:
                return None

            files_destination = self.config.get("files_destination", "")

        return os.path.expanduser(files_destination)

    @property
    def media_destination(self):
        if not self.args.media == None:
            media_destination = self.args.media
        else:
            if not self.config:
                return None

            media_destination = self.config.get("media_destination", "")

        return os.path.expanduser(media_destination)


try:
    CONFIG = Config()
except ConfigError as err:
    print(str(err))
    print("Aborting...")
    exit(1)
