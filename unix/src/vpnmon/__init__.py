"""VPN Connect Monitoring — контроль подключения VPN в рабочее время."""

__version__ = "2.2.2"

APP_ID = "vpn-connect-monitoring"
APP_TITLE = "VPN Connect Monitoring"


def bundle_path():
    """Путь к пакету .app, если код запущен из него, иначе None.

    Внутри пакета код лежит в Contents/Resources/lib/vpnmon, поэтому
    подниматься нужно на четыре уровня.
    """
    import os

    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    contents = os.path.dirname(os.path.dirname(package_root))
    bundle = os.path.dirname(contents)

    if os.path.basename(contents) == "Contents" and bundle.endswith(".app"):
        return bundle
    return None
