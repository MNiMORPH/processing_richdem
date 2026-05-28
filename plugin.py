from qgis.core import QgsApplication
from .provider import RichDEMProvider


class RichDEMPlugin:
    def __init__(self, iface):
        self.provider = None

    def initGui(self):
        self.provider = RichDEMProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        QgsApplication.processingRegistry().removeProvider(self.provider)
