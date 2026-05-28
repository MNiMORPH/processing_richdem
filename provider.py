from qgis.core import QgsProcessingProvider

from .algorithms.fill_depressions import FillDepressionsAlgorithm
from .algorithms.breach_depressions import BreachDepressionsAlgorithm
from .algorithms.resolve_flats import ResolveFlatsAlgorithm
from .algorithms.flow_accumulation import FlowAccumulationAlgorithm
from .algorithms.terrain_attribute import TerrainAttributeAlgorithm
from .algorithms.depression_hierarchy import DepressionHierarchyAlgorithm
from .algorithms.fill_spill_merge import FillSpillMergeAlgorithm


class RichDEMProvider(QgsProcessingProvider):
    def id(self):
        return 'richdem'

    def name(self):
        return 'RichDEM'

    def longName(self):
        return 'RichDEM Terrain Analysis'

    def loadAlgorithms(self):
        for cls in [
            FillDepressionsAlgorithm,
            BreachDepressionsAlgorithm,
            ResolveFlatsAlgorithm,
            FlowAccumulationAlgorithm,
            TerrainAttributeAlgorithm,
            DepressionHierarchyAlgorithm,
            FillSpillMergeAlgorithm,
        ]:
            self.addAlgorithm(cls())
