from .plugin import RichDEMPlugin


def classFactory(iface):
    return RichDEMPlugin(iface)
