from app.core.plugin_manager import PluginManager
from app.services.stream_service import StreamService


def main():
    manager = PluginManager()
    manager.load_plugins()

    stream = StreamService(manager)

    stream.update_title("twitch", "StreamTail test stream")
    stream.update_game("twitch", "Minecraft")

    print(stream.check_live("twitch"))


if __name__ == "__main__":
    main()
