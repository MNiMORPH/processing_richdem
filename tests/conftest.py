"""Pytest configuration: initialise a headless QGIS application and create
synthetic test DEMs shared across all tests.

Bowl DEM (7×7, 1 m resolution) — used for fill/breach/dephier/fsm:

    5 5 5 5 5 5 5
    5 5 5 5 5 5 5
    5 5 3 3 3 5 5
    5 5 9 9 9 5 5
    5 5 9 1 4 5 5   <- pit=1, step=4 adjacent to outer region (5)
    5 5 9 9 9 5 5
    5 5 5 5 5 5 5
    5 5 5 5 5 5 5

The 1-cell-wide inner ring (9) encloses the pit (1) except for the step
(4), which sits directly between the pit and the outer region (5).  All
three depression-resolving algorithms produce distinct, comparable results:
  fill              => min=5.0 (pit and step raised to pour-point 5)
  CompleteBreaching => min=4.0 (pit raised to step; step preserved)
  Lindsay2016 eps   => min<4.0 (pit shallowed to just below step)

Slope DEM (7×7, 1 m resolution) — used for flow accumulation:

    6 6 6 6 6 6 6   (row 1, north)
    5 5 5 5 5 5 5
    4 4 4 4 4 4 4
    3 3 3 3 3 3 3
    2 2 2 2 2 2 2
    1 1 1 1 1 1 1
    0 0 0 0 0 0 0   (row 7, south)

No depressions or flat areas; all cells drain unambiguously southward.
"""

import os
import sys

# Must be set before any GDAL/PROJ/QGIS import to prevent Anaconda's
# stale proj.db (version 2) from being loaded instead of the system one.
os.environ['PROJ_DATA'] = '/usr/share/proj'
os.environ.setdefault('QGIS_PREFIX_PATH', '/usr')

from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal, osr

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

_GT = (0.0, 1.0, 0.0, 7.0, 0.0, -1.0)   # 1 m cells, top-left origin
_EPSG = 32614

_BOWL = np.array([
    [5, 5, 5, 5, 5, 5, 5],
    [5, 5, 5, 5, 5, 5, 5],
    [5, 5, 9, 9, 9, 5, 5],
    [5, 5, 9, 1, 4, 5, 5],   # pit at (3,3)=1; step at (3,4)=4
    [5, 5, 9, 9, 9, 5, 5],
    [5, 5, 5, 5, 5, 5, 5],
    [5, 5, 5, 5, 5, 5, 5],
], dtype=np.float64)

_SLOPE = np.array([
    [6, 6, 6, 6, 6, 6, 6],
    [5, 5, 5, 5, 5, 5, 5],
    [4, 4, 4, 4, 4, 4, 4],
    [3, 3, 3, 3, 3, 3, 3],
    [2, 2, 2, 2, 2, 2, 2],
    [1, 1, 1, 1, 1, 1, 1],
    [0, 0, 0, 0, 0, 0, 0],
], dtype=np.float64)


# Module-level reference prevents the provider from being garbage-collected
# while QGIS holds only a C++ pointer to it (classic PyQGIS ownership issue).
_PROVIDER = None


def pytest_configure(config):
    global _PROVIDER

    from qgis.testing import start_app
    start_app()

    # Initialize the Processing framework and register our provider.
    sys.path.insert(0, '/usr/share/qgis/python/plugins')
    from processing.core.Processing import Processing
    Processing.initialize()

    from processing_richdem.provider import RichDEMProvider
    from qgis.core import QgsApplication
    _PROVIDER = RichDEMProvider()
    QgsApplication.processingRegistry().addProvider(_PROVIDER)


def write_tif(data, path, nodata=-9999.0, epsg=_EPSG):
    """Write a float64 GeoTIFF and return the path string."""
    rows, cols = data.shape
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(str(path), cols, rows, 1, gdal.GDT_Float64)
    ds.SetGeoTransform(_GT)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.WriteArray(data)
    band.SetNoDataValue(nodata)
    ds.FlushCache()
    ds = None
    return str(path)


@pytest.fixture(scope='session')
def tmp_dir(tmp_path_factory):
    return tmp_path_factory.mktemp('richdem')


@pytest.fixture(scope='session')
def bowl_tif(tmp_dir):
    return write_tif(_BOWL, tmp_dir / 'bowl.tif')


@pytest.fixture(scope='session')
def slope_tif(tmp_dir):
    return write_tif(_SLOPE, tmp_dir / 'slope.tif')


@pytest.fixture(scope='session')
def bowl_layer(bowl_tif):
    from qgis.core import QgsRasterLayer
    layer = QgsRasterLayer(bowl_tif, 'bowl')
    assert layer.isValid()
    return layer


@pytest.fixture(scope='session')
def slope_layer(slope_tif):
    from qgis.core import QgsRasterLayer
    layer = QgsRasterLayer(slope_tif, 'slope')
    assert layer.isValid()
    return layer
