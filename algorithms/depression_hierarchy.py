from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorDestination,
)


class DepressionHierarchyAlgorithm(QgsProcessingAlgorithm):
    """Build a RichDEM depression hierarchy (Barnes 2020) for Fill-Spill-Merge."""

    INPUT            = 'INPUT'
    OUTPUT_LABELS    = 'OUTPUT_LABELS'
    OUTPUT_FLOWDIRS  = 'OUTPUT_FLOWDIRS'
    OUTPUT_HIERARCHY = 'OUTPUT_HIERARCHY'

    def name(self):
        return 'depressionhierarchy'

    def displayName(self):
        return 'Depression Hierarchy'

    def group(self):
        return 'Hydrology'

    def groupId(self):
        return 'hydrology'

    def shortHelpString(self):
        return (
            'Compute the depression hierarchy of a DEM using RichDEM.\n\n'
            'Outputs a depression labels raster, a flow directions raster, and a '
            'GeoPackage containing the full depression hierarchy (required as input '
            'for the Fill-Spill-Merge algorithm).\n\n'
            'Requires: pip install richdem'
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, 'Input elevation raster'))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_LABELS, 'Output depression labels raster'))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_FLOWDIRS, 'Output flow directions raster'))
        self.addParameter(QgsProcessingParameterVectorDestination(
            self.OUTPUT_HIERARCHY,
            'Output depression hierarchy GeoPackage'))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            import richdem as rd
        except ImportError:
            raise QgsProcessingException(
                'richdem is not installed. Run: pip install richdem')

        from ..richdem_utils.raster import rdarray_from_layer, rdarray_to_file
        from ..richdem_utils.vector import depressions_to_gpkg

        dem_layer        = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        labels_path      = self.parameterAsOutputLayer(parameters, self.OUTPUT_LABELS, context)
        flowdirs_path    = self.parameterAsOutputLayer(parameters, self.OUTPUT_FLOWDIRS, context)
        hierarchy_path   = self.parameterAsOutputLayer(parameters, self.OUTPUT_HIERARCHY, context)

        feedback.setProgress(5)
        dem = rdarray_from_layer(dem_layer)
        proj = getattr(dem, '_projection', None)

        feedback.setProgress(15)
        labels = rd.get_new_depression_hierarchy_labels(
            dem.shape, geotransform=dem.geotransform)
        labels._projection = proj

        feedback.setProgress(20)
        deps, flowdirs = rd.get_depression_hierarchy(dem, labels)
        flowdirs._projection = proj

        feedback.setProgress(60)
        rdarray_to_file(labels, labels_path, projection=proj)
        rdarray_to_file(flowdirs, flowdirs_path, projection=proj)

        feedback.setProgress(70)
        depressions_to_gpkg(deps, labels, hierarchy_path)
        feedback.setProgress(100)

        return {
            self.OUTPUT_LABELS:    labels_path,
            self.OUTPUT_FLOWDIRS:  flowdirs_path,
            self.OUTPUT_HIERARCHY: hierarchy_path,
        }

    def createInstance(self):
        return DepressionHierarchyAlgorithm()
