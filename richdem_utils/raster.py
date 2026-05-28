"""Conversion between QGIS raster layers / file paths and RichDEM rdarray objects."""

import numpy as np
from osgeo import gdal
import richdem as rd

_NO_DATA = -9999.0


def rdarray_from_layer(layer):
    """Read a QgsRasterLayer into a RichDEM rdarray.

    Stashes the WKT projection on rda._projection for use when writing output.
    """
    ds = gdal.Open(layer.source())
    gt = ds.GetGeoTransform()  # (west, ewres, 0, north, 0, -nsres) — same format as rdarray
    band = ds.GetRasterBand(1)
    data = band.ReadAsArray().astype(np.float64)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        data[data == nodata] = _NO_DATA
    data[np.isnan(data)] = _NO_DATA
    rda = rd.rdarray(data, no_data=_NO_DATA, geotransform=gt)
    rda._projection = ds.GetProjection()
    return rda


def rdarray_to_file(rda, output_path, projection=None):
    """Write a RichDEM rdarray to a GeoTIFF file."""
    data = np.array(rda, dtype=np.float64)
    data[(data == rda.no_data) | np.isnan(data)] = _NO_DATA
    rows, cols = data.shape
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(output_path, cols, rows, 1, gdal.GDT_Float64)
    ds.SetGeoTransform(rda.geotransform)
    if projection:
        ds.SetProjection(projection)
    band = ds.GetRasterBand(1)
    band.WriteArray(data)
    band.SetNoDataValue(_NO_DATA)
    ds.FlushCache()
    ds = None
