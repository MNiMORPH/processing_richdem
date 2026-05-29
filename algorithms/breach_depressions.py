from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
)


class BreachDepressionsAlgorithm(QgsProcessingAlgorithm):
    INPUT    = 'INPUT'
    OUTPUT   = 'OUTPUT'
    TOPOLOGY = 'TOPOLOGY'
    EPSILON  = 'EPSILON'

    def name(self):
        return 'breachdepressions'

    def displayName(self):
        return 'Breach Depressions'

    def group(self):
        return 'Hydrology'

    def groupId(self):
        return 'hydrology'

    def shortHelpString(self):
        return (
            'Breach depressions in a DEM by carving least-cost channels '
            '(Lindsay 2016).\n\n'
            'Enable "epsilon gradients" to shallow pits to just below the '
            'saddle elevation rather than raising them to exactly the saddle.\n\n'
            'Requires: pip install richdem'
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, 'Input elevation raster'))
        self.addParameter(QgsProcessingParameterEnum(
            self.TOPOLOGY, 'Flow topology', options=['D8', 'D4'], defaultValue=0))
        self.addParameter(QgsProcessingParameterBoolean(
            self.EPSILON, 'Use epsilon gradients (shallow pits to just below saddle)',
            defaultValue=False))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, 'Output depression-breached elevation raster'))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            import richdem as rd
        except ImportError:
            raise QgsProcessingException(
                'richdem is not installed. Run: pip install richdem')

        from ..richdem_utils.raster import rdarray_from_layer, rdarray_to_file

        dem_layer   = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        topology    = ['D8', 'D4'][self.parameterAsEnum(parameters, self.TOPOLOGY, context)]
        epsilon     = self.parameterAsBoolean(parameters, self.EPSILON, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        feedback.setProgress(10)
        dem = rdarray_from_layer(dem_layer)
        feedback.setProgress(40)
        if epsilon:
            if not hasattr(rd, 'BreachDepressionsEps'):
                raise QgsProcessingException(
                    'Epsilon breaching (BreachDepressionsEps) is not available '
                    'in this RichDEM build.')
            # BreachDepressionsEps (Lindsay2016) only supports D8 topology.
            breached = rd.BreachDepressionsEps(dem)
        else:
            breached = rd.BreachDepressions(dem, topology=topology)
        feedback.setProgress(80)
        rdarray_to_file(breached, output_path, projection=getattr(dem, '_projection', None))
        feedback.setProgress(100)

        return {self.OUTPUT: output_path}

    def createInstance(self):
        return BreachDepressionsAlgorithm()
