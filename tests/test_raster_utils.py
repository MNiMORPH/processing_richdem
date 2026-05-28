"""Tests for richdem_utils/raster.py.

Uses a lightweight MockLayer (only .source() is needed) so these tests
run without the full QGIS Processing machinery.
"""

import numpy as np
import pytest
from osgeo import gdal


class MockLayer:
    def __init__(self, path):
        self._path = str(path)

    def source(self):
        return self._path


def test_shape(bowl_tif):
    from processing_richdem.richdem_utils.raster import rdarray_from_layer
    rda = rdarray_from_layer(MockLayer(bowl_tif))
    assert rda.shape == (7, 7)


def test_geotransform(bowl_tif):
    """Geotransform (west, ewres, 0, north, 0, -nsres) is preserved exactly."""
    from processing_richdem.richdem_utils.raster import rdarray_from_layer
    gt = rdarray_from_layer(MockLayer(bowl_tif)).geotransform
    assert gt[0] == pytest.approx(0.0)    # west
    assert gt[1] == pytest.approx(1.0)    # ewres
    assert gt[3] == pytest.approx(7.0)    # north
    assert gt[5] == pytest.approx(-1.0)   # -nsres


def test_projection_stashed(bowl_tif):
    """WKT projection is stored on rda._projection for output writers."""
    from processing_richdem.richdem_utils.raster import rdarray_from_layer
    rda = rdarray_from_layer(MockLayer(bowl_tif))
    assert hasattr(rda, '_projection')
    assert 'PROJCS' in rda._projection or 'GEOGCS' in rda._projection


def test_round_trip_values(bowl_tif, tmp_dir):
    """Non-nodata values survive a read → write → read round-trip."""
    from processing_richdem.richdem_utils.raster import rdarray_from_layer, rdarray_to_file
    rda = rdarray_from_layer(MockLayer(bowl_tif))
    out = str(tmp_dir / 'roundtrip.tif')
    rdarray_to_file(rda, out, projection=rda._projection)

    ds = gdal.Open(out)
    data = ds.GetRasterBand(1).ReadAsArray()
    nodata = ds.GetRasterBand(1).GetNoDataValue()
    ds = None

    original = np.array(rda)
    mask = original != rda.no_data
    assert np.allclose(data[mask], original[mask])


def test_round_trip_nodata_value(bowl_tif, tmp_dir):
    """Output GeoTIFF uses -9999 as the nodata sentinel."""
    from processing_richdem.richdem_utils.raster import rdarray_from_layer, rdarray_to_file
    rda = rdarray_from_layer(MockLayer(bowl_tif))
    out = str(tmp_dir / 'roundtrip_nodata.tif')
    rdarray_to_file(rda, out, projection=rda._projection)

    ds = gdal.Open(out)
    nodata = ds.GetRasterBand(1).GetNoDataValue()
    ds = None
    assert nodata == pytest.approx(-9999.0)
