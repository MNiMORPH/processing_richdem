from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
)


class FillDepressionsAlgorithm(QgsProcessingAlgorithm):
    INPUT    = 'INPUT'
    OUTPUT   = 'OUTPUT'
    TOPOLOGY = 'TOPOLOGY'
    EPSILON  = 'EPSILON'

    def name(self):
        return 'filldepressions'

    def displayName(self):
        return 'Fill Depressions'

    def group(self):
        return 'Hydrology'

    def groupId(self):
        return 'hydrology'

    def shortHelpString(self):
        return (
            'Fill depressions in a DEM using the RichDEM Priority-Flood algorithm.\n\n'
            'Requires: pip install richdem'
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, 'Input elevation raster'))
        self.addParameter(QgsProcessingParameterEnum(
            self.TOPOLOGY, 'Flow topology', options=['D8', 'D4'], defaultValue=0))
        self.addParameter(QgsProcessingParameterBoolean(
            self.EPSILON, 'Apply epsilon gradient to flat areas after filling',
            defaultValue=False))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, 'Output depression-filled elevation raster'))

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
        filled = rd.FillDepressions(dem, epsilon=epsilon, topology=topology)
        feedback.setProgress(80)
        rdarray_to_file(filled, output_path, projection=getattr(dem, '_projection', None))
        feedback.setProgress(100)

        return {self.OUTPUT: output_path}

    def createInstance(self):
        return FillDepressionsAlgorithm()
