import shutil

import numpy as np
from osgeo import gdal

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
)


class FillSpillMergeAlgorithm(QgsProcessingAlgorithm):
    INPUT            = 'INPUT'
    LABELS           = 'LABELS'
    FLOWDIRS         = 'FLOWDIRS'
    HIERARCHY        = 'HIERARCHY'
    WATER_DEPTH      = 'WATER_DEPTH'
    WATER_DEPTH_SCALAR = 'WATER_DEPTH_SCALAR'
    OUTPUT_WTD       = 'OUTPUT_WTD'
    OUTPUT_HIERARCHY = 'OUTPUT_HIERARCHY'

    def name(self):
        return 'fillspillmerge'

    def displayName(self):
        return 'Fill-Spill-Merge'

    def group(self):
        return 'Hydrology'

    def groupId(self):
        return 'hydrology'

    def shortHelpString(self):
        return (
            'Apply one Fill-Spill-Merge step to redistribute surface water through '
            'the depression hierarchy without removing depressions.\n\n'
            'Run Depression Hierarchy first to generate the labels, flow directions, '
            'and hierarchy GeoPackage inputs.\n\n'
            'The output hierarchy GeoPackage is a copy of the input with updated '
            'water_vol values per depression.\n\n'
            'Requires: pip install richdem'
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.INPUT, 'Input elevation raster'))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.LABELS, 'Depression labels raster (from Depression Hierarchy)'))
        self.addParameter(QgsProcessingParameterRasterLayer(
            self.FLOWDIRS, 'Flow directions raster (from Depression Hierarchy)'))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.HIERARCHY, 'Depression hierarchy GeoPackage (from Depression Hierarchy)'))
        water_depth = QgsProcessingParameterRasterLayer(
            self.WATER_DEPTH,
            'Input water depth raster (negative = below surface, positive = surface water)',
            optional=True)
        self.addParameter(water_depth)
        self.addParameter(QgsProcessingParameterNumber(
            self.WATER_DEPTH_SCALAR,
            'Uniform water depth scalar (used if no raster supplied)',
            type=QgsProcessingParameterNumber.Double,
            defaultValue=0.0))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_WTD, 'Output water depth raster after redistribution'))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.OUTPUT_HIERARCHY,
            'Output hierarchy GeoPackage with updated water volumes',
            fileFilter='GeoPackage (*.gpkg)'))

    def processAlgorithm(self, parameters, context, feedback):
        try:
            import richdem as rd
        except ImportError:
            raise QgsProcessingException(
                'richdem is not installed. Run: pip install richdem')

        from ..richdem_utils.raster import rdarray_from_layer, rdarray_to_file
        from ..richdem_utils.vector import depressions_from_gpkg, update_water_vol

        dem_layer      = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        labels_layer   = self.parameterAsRasterLayer(parameters, self.LABELS, context)
        flowdirs_layer = self.parameterAsRasterLayer(parameters, self.FLOWDIRS, context)
        hierarchy_layer = self.parameterAsVectorLayer(parameters, self.HIERARCHY, context)
        hierarchy_path  = hierarchy_layer.source().split('|')[0]
        wtd_layer      = self.parameterAsRasterLayer(parameters, self.WATER_DEPTH, context)
        wtd_scalar     = self.parameterAsDouble(parameters, self.WATER_DEPTH_SCALAR, context)
        output_wtd     = self.parameterAsOutputLayer(parameters, self.OUTPUT_WTD, context)
        output_hier    = self.parameterAsFileOutput(parameters, self.OUTPUT_HIERARCHY, context)

        feedback.setProgress(5)
        dem  = rdarray_from_layer(dem_layer)
        proj = getattr(dem, '_projection', None)

        if wtd_layer is None and wtd_scalar == 0.0:
            feedback.pushInfo(
                'Water depth is zero everywhere — skipping FSM computation '
                'and returning the input unchanged. (Your CPU thanks you.)')
            rows, cols = dem.shape
            ds = gdal.GetDriverByName('GTiff').Create(
                output_wtd, cols, rows, 1, gdal.GDT_Float64)
            ds.SetGeoTransform(dem.geotransform)
            if proj:
                ds.SetProjection(proj)
            band = ds.GetRasterBand(1)
            band.SetNoDataValue(-9999.0)
            band.WriteArray(np.zeros((rows, cols), dtype=np.float64))
            ds.FlushCache()
            ds = None
            shutil.copy2(hierarchy_path, output_hier)
            return {self.OUTPUT_WTD: output_wtd, self.OUTPUT_HIERARCHY: output_hier}

        if wtd_layer is not None:
            wtd = rdarray_from_layer(wtd_layer)
        else:
            wtd = rd.rdarray(
                np.full(dem.shape, wtd_scalar, dtype=np.float64),
                no_data=-9999.0, geotransform=dem.geotransform)
            wtd._projection = proj

        # FSM requires labels as uint32 and flowdirs as int8;
        # rdarray_from_layer reads float64, so we cast after reading.
        _lf = rdarray_from_layer(labels_layer)
        _ff = rdarray_from_layer(flowdirs_layer)
        labels   = rd.rdarray(np.array(_lf, dtype=np.uint32),
                              no_data=2**32 - 1, geotransform=_lf.geotransform)
        flowdirs = rd.rdarray(np.array(_ff, dtype=np.int8),
                              no_data=-1, geotransform=_ff.geotransform)

        feedback.setProgress(20)
        deps = depressions_from_gpkg(hierarchy_path)

        feedback.setProgress(30)
        rd.fill_spill_merge(dem, labels, flowdirs, deps, wtd)

        # pybind11/stl.h copies the Depression vector in and out without
        # writing back mutable-reference changes, so deps[i].water_vol is
        # unchanged after the call.  Recompute from the output wtd array.
        labels_arr = np.array(labels, dtype=np.int64)
        wtd_arr    = np.array(wtd)
        cell_area  = abs(dem.geotransform[1] * dem.geotransform[5])
        label_to_dep = {d.dep_label: d for d in deps}
        for dep_label in np.unique(labels_arr):
            if dep_label in label_to_dep:
                mask = labels_arr == dep_label
                label_to_dep[dep_label].water_vol = float(
                    np.sum(np.maximum(wtd_arr[mask], 0.0)) * cell_area
                )

        feedback.setProgress(80)
        rdarray_to_file(wtd, output_wtd, projection=proj)

        shutil.copy2(hierarchy_path, output_hier)
        update_water_vol(deps, output_hier)
        feedback.setProgress(100)

        return {
            self.OUTPUT_WTD:       output_wtd,
            self.OUTPUT_HIERARCHY: output_hier,
        }

    def createInstance(self):
        return FillSpillMergeAlgorithm()
