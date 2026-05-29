from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
)

_ATTRIBUTES = [
    'slope_riserun', 'slope_percentage', 'slope_degrees', 'slope_radians',
    'aspect', 'curvature', 'planform_curvature', 'profile_curvature',
]


class TerrainAttributeAlgorithm(QgsProcessingAlgorithm):
    """Compute slope, aspect, or curvature from a DEM via RichDEM."""

    INPUT     = 'INPUT'
    OUTPUT    = 'OUTPUT'
    ATTRIBUTE = 'ATTRIBUTE'
    ZSCALE    = 'ZSCALE'

    def name(self):
        return 'terrainattribute'

    def displayName(self):
        return 'Terrain Attribute'

    def group(self):
        return 'Terrain'

    def groupId(self):
        return 'terrain'

    def shortHelpString(self):
        return (
            'Calculate a terrain attribute (slope, aspect, or curvature) '
            'from a DEM using RichDEM.\n\nRequires: pip install richdem'
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, 'Input elevation raster'))
        self.addParameter(QgsProcessingParameterEnum(
            self.ATTRIBUTE, 'Terrain attribute',
            options=_ATTRIBUTES, defaultValue=2))  # slope_degrees default
        self.addParameter(QgsProcessingParameterNumber(
            self.ZSCALE, 'Z-axis scale factor',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=1.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, 'Output terrain attribute raster'))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            import richdem as rd
        except ImportError:
            raise QgsProcessingException(
                'richdem is not installed. Run: pip install richdem')

        from ..richdem_utils.raster import rdarray_from_layer, rdarray_to_file

        dem_layer   = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        attribute   = _ATTRIBUTES[self.parameterAsEnum(parameters, self.ATTRIBUTE, context)]
        zscale      = self.parameterAsDouble(parameters, self.ZSCALE, context)
        output_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        feedback.setProgress(10)
        dem = rdarray_from_layer(dem_layer)
        feedback.setProgress(40)
        result = rd.TerrainAttribute(dem, attrib=attribute, zscale=zscale)
        feedback.setProgress(80)
        rdarray_to_file(result, output_path, projection=getattr(dem, '_projection', None))
        feedback.setProgress(100)

        return {self.OUTPUT: output_path}

    def createInstance(self):
        return TerrainAttributeAlgorithm()
