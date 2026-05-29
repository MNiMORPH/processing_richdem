from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
)


class ResolveFlatsAlgorithm(QgsProcessingAlgorithm):
    """Add gradient to flat regions so flow can be routed through them (Barnes 2014)."""

    INPUT  = 'INPUT'
    OUTPUT = 'OUTPUT'

    def name(self):
        return 'resolveflats'

    def displayName(self):
        return 'Resolve Flats'

    def group(self):
        return 'Hydrology'

    def groupId(self):
        return 'hydrology'

    def shortHelpString(self):
        return (
            'Impose an epsilon gradient on flat areas of a DEM to ensure '
            'unique flow directions.\n\nRequires: pip install richdem'
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, 'Input elevation raster'))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, 'Output elevation raster with resolved flats'))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            import richdem as rd
        except ImportError:
            raise QgsProcessingException(
                'richdem is not installed. Run: pip install richdem')

        from ..richdem_utils.raster import rdarray_from_layer, rdarray_to_file

        dem_layer   = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        feedback.setProgress(10)
        dem = rdarray_from_layer(dem_layer)
        feedback.setProgress(40)
        resolved = rd.ResolveFlats(dem)
        feedback.setProgress(80)
        rdarray_to_file(resolved, output_path, projection=getattr(dem, '_projection', None))
        feedback.setProgress(100)

        return {self.OUTPUT: output_path}

    def createInstance(self):
        return ResolveFlatsAlgorithm()
