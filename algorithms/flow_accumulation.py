from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
)

_METHODS = [
    'D8', 'D4', 'Dinf', 'Tarboton', 'Quinn', 'Holmgren', 'Freeman',
    'Rho8', 'Rho4', 'FairfieldLeymarieD8', 'FairfieldLeymarieD4',
    'OCallaghanD8', 'OCallaghanD4',
]
_EXPONENT_METHODS = {'Holmgren', 'Freeman'}


class FlowAccumulationAlgorithm(QgsProcessingAlgorithm):
    INPUT    = 'INPUT'
    OUTPUT   = 'OUTPUT'
    METHOD   = 'METHOD'
    EXPONENT = 'EXPONENT'
    WEIGHTS  = 'WEIGHTS'

    def name(self):
        return 'flowaccumulation'

    def displayName(self):
        return 'Flow Accumulation'

    def group(self):
        return 'Hydrology'

    def groupId(self):
        return 'hydrology'

    def shortHelpString(self):
        return (
            'Calculate flow accumulation using one of 13 single- or '
            'multiple-flow-direction algorithms from RichDEM.\n\n'
            'Holmgren and Freeman methods require an exponent value.\n\n'
            'Requires: pip install richdem'
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, 'Input elevation raster'))
        self.addParameter(QgsProcessingParameterEnum(
            self.METHOD, 'Flow accumulation method',
            options=_METHODS, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.EXPONENT, 'Exponent (Holmgren / Freeman methods only)',
            type=QgsProcessingParameterNumber.Double,
            optional=True, minValue=0.0))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.WEIGHTS, 'Flow accumulation weights (optional)',
            optional=True))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT, 'Output flow accumulation raster'))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            import richdem as rd
        except ImportError:
            raise QgsProcessingException(
                'richdem is not installed. Run: pip install richdem')

        from ..richdem_utils.raster import rdarray_from_layer, rdarray_to_file

        dem_layer    = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        method       = _METHODS[self.parameterAsEnum(parameters, self.METHOD, context)]
        output_path  = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        exponent = None
        if self.parameterAsDouble(parameters, self.EXPONENT, context) is not None:
            exponent = self.parameterAsDouble(parameters, self.EXPONENT, context)

        if method in _EXPONENT_METHODS and exponent is None:
            raise QgsProcessingException(
                f'Method {method} requires an exponent value.')

        weights_layer = self.parameterAsRasterLayer(parameters, self.WEIGHTS, context)

        feedback.setProgress(10)
        dem = rdarray_from_layer(dem_layer)
        weights = rdarray_from_layer(weights_layer) if weights_layer else None
        feedback.setProgress(40)
        accum = rd.FlowAccumulation(dem, method=method, exponent=exponent, weights=weights)
        feedback.setProgress(80)
        rdarray_to_file(accum, output_path, projection=getattr(dem, '_projection', None))
        feedback.setProgress(100)

        return {self.OUTPUT: output_path}

    def createInstance(self):
        return FlowAccumulationAlgorithm()
