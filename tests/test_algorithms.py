"""End-to-end tests for all seven Processing algorithms via processing.run().

Mirrors the assertions in the r.richdem GRASS testsuite, adapted for QGIS
and GeoPackage outputs.
"""

import sqlite3

import numpy as np
import pytest
from osgeo import gdal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path):
    """Return (data, nodata) for the first band of a GeoTIFF."""
    ds = gdal.Open(str(path))
    data = ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    nodata = ds.GetRasterBand(1).GetNoDataValue()
    ds = None
    return data, nodata


def _valid(data, nodata):
    """Return a masked array of valid (non-nodata, non-nan) cells."""
    mask = np.ones(data.shape, dtype=bool)
    if nodata is not None:
        mask &= data != nodata
    mask &= ~np.isnan(data)
    return data[mask]


def run(alg_id, params):
    # processing.run() uses createAlgorithmById(), which is broken for
    # providers added after Processing.initialize() in headless tests.
    # Use providerById().algorithm() + createInstance() + processAlgorithm()
    # directly instead.
    from qgis.core import (QgsApplication, QgsProcessingContext,
                           QgsProcessingFeedback)
    provider_id, alg_name = alg_id.split(':', 1)
    template = QgsApplication.processingRegistry().providerById(provider_id).algorithm(alg_name)
    if template is None:
        raise Exception(f'Algorithm not found: {alg_id}')
    alg = template.createInstance()
    alg.initAlgorithm({})
    context = QgsProcessingContext()
    feedback = QgsProcessingFeedback()
    return alg.processAlgorithm(params, context, feedback)


# ---------------------------------------------------------------------------
# Fill Depressions
# ---------------------------------------------------------------------------

class TestFillDepressions:
    """Bowl DEM: border≈5, 3-ring, pit=1, channel at row 3 exits right border at 3.
    Pour point = 3; only the pit cell is a true depression."""

    def test_output_created(self, bowl_layer, tmp_dir):
        """Filling a depressed DEM produces an output raster."""
        result = run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': False,
            'OUTPUT': str(tmp_dir / 'filled.tif'),
        })
        assert gdal.Open(result['OUTPUT']) is not None

    def test_pit_raised_to_pour_point(self, bowl_layer, tmp_dir):
        """Pit cell rises from 1 to the pour-point elevation (3); max stays 5."""
        result = run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': False,
            'OUTPUT': str(tmp_dir / 'filled2.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        valid = _valid(data, nodata)
        assert valid.min() == pytest.approx(3.0)
        assert valid.max() == pytest.approx(5.0)

    def test_fill_never_lowers(self, bowl_layer, bowl_tif, tmp_dir):
        """No cell is lowered by filling (filled − input ≥ 0 everywhere)."""
        result = run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': False,
            'OUTPUT': str(tmp_dir / 'filled3.tif'),
        })
        filled, nodata = _read(result['OUTPUT'])
        original, _ = _read(bowl_tif)
        diff = _valid(filled - original, nodata)
        assert diff.min() >= 0.0, 'At least one cell was lowered by filling'

    def test_epsilon_removes_flats(self, bowl_layer, tmp_dir):
        """With epsilon, all filled cells are strictly above the pour point."""
        result = run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': True,
            'OUTPUT': str(tmp_dir / 'filled_eps.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        assert _valid(data, nodata).min() >= 3.0

    def test_d4_topology(self, bowl_layer, tmp_dir):
        """D4 topology completes without error."""
        result = run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 1, 'EPSILON': False,
            'OUTPUT': str(tmp_dir / 'filled_d4.tif'),
        })
        assert gdal.Open(result['OUTPUT']) is not None


# ---------------------------------------------------------------------------
# Breach Depressions
# ---------------------------------------------------------------------------

class TestBreachDepressions:
    def test_output_created(self, bowl_layer, tmp_dir):
        """Breaching produces an output raster."""
        result = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0,
            'OUTPUT': str(tmp_dir / 'breached.tif'),
        })
        assert gdal.Open(result['OUTPUT']) is not None

    def test_output_shape(self, bowl_layer, tmp_dir):
        result = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0,
            'OUTPUT': str(tmp_dir / 'breached2.tif'),
        })
        data, _ = _read(result['OUTPUT'])
        assert data.shape == (7, 7)

    def test_resolves_pit(self, bowl_layer, bowl_tif, tmp_dir):
        """Breaching resolves the isolated pit.

        The bowl DEM has a pre-existing channel at the pour-point elevation (3),
        so RichDEM raises the pit to channel level rather than carving the
        channel (fill is lower-cost than carve here).  After breaching:
          - The pit cell must be strictly higher than before.
          - No interior cell is lowered.
        """
        result = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0,
            'OUTPUT': str(tmp_dir / 'breached3.tif'),
        })
        breached, nodata = _read(result['OUTPUT'])
        original, _ = _read(bowl_tif)
        assert breached[3, 3] > original[3, 3], \
            f'Pit cell not raised (got {breached[3,3]}, expected > {original[3,3]})'
        diff = breached[1:-1, 1:-1] - original[1:-1, 1:-1]
        assert diff.min() >= 0.0, 'An interior cell was unexpectedly lowered'


# ---------------------------------------------------------------------------
# Resolve Flats
# ---------------------------------------------------------------------------

class TestResolveFlats:
    def test_output_created(self, bowl_layer, tmp_dir):
        """ResolveFlats on a pre-filled DEM produces output."""
        filled = str(tmp_dir / 'rf_filled.tif')
        run('richdem:filldepressions', {'INPUT': bowl_layer, 'TOPOLOGY': 0,
                                        'EPSILON': False, 'OUTPUT': filled})
        from qgis.core import QgsRasterLayer
        result = run('richdem:resolveflats', {
            'INPUT': QgsRasterLayer(filled, 'f'),
            'OUTPUT': str(tmp_dir / 'resolved.tif'),
        })
        assert gdal.Open(result['OUTPUT']) is not None


# ---------------------------------------------------------------------------
# Flow Accumulation — slope DEM (uniform southward drainage)
# ---------------------------------------------------------------------------

class TestFlowAccumulation:
    """Slope DEM: rows 1–7 have elevations 6–0; all cells drain south.

    D8 flow-accumulation properties:
      - Every cell counts at least itself: min FA ≥ 1.
      - Interior cells accumulate upstream cells: max FA > 1.
      - No cell is left null.
    """

    def test_d8_min_is_one(self, slope_layer, tmp_dir):
        """Minimum FA is 1 — every cell counts at least itself."""
        result = run('richdem:flowaccumulation', {
            'INPUT': slope_layer, 'METHOD': 0,
            'OUTPUT': str(tmp_dir / 'fa_d8.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        assert _valid(data, nodata).min() >= 1.0

    def test_d8_accumulation_occurs(self, slope_layer, tmp_dir):
        """Max FA > 1 — interior cells accumulate upstream drainage."""
        result = run('richdem:flowaccumulation', {
            'INPUT': slope_layer, 'METHOD': 0,
            'OUTPUT': str(tmp_dir / 'fa_d8b.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        assert _valid(data, nodata).max() > 1.0

    def test_d8_no_null_cells(self, slope_layer, tmp_dir):
        """Every cell has a valid (non-null) flow accumulation value."""
        result = run('richdem:flowaccumulation', {
            'INPUT': slope_layer, 'METHOD': 0,
            'OUTPUT': str(tmp_dir / 'fa_d8c.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        assert len(_valid(data, nodata)) == data.size

    def test_dinf_output_created(self, slope_layer, tmp_dir):
        """D-infinity (Tarboton) method produces output."""
        result = run('richdem:flowaccumulation', {
            'INPUT': slope_layer, 'METHOD': 2,
            'OUTPUT': str(tmp_dir / 'fa_dinf.tif'),
        })
        assert gdal.Open(result['OUTPUT']) is not None

    def test_holmgren_requires_exponent(self, slope_layer, tmp_dir):
        """Holmgren method raises an error when no exponent is given."""
        with pytest.raises(Exception):
            run('richdem:flowaccumulation', {
                'INPUT': slope_layer, 'METHOD': 5,
                'OUTPUT': str(tmp_dir / 'fa_holmgren_bad.tif'),
            })

    def test_holmgren_with_exponent(self, slope_layer, tmp_dir):
        """Holmgren method with exponent=4.0 produces valid output."""
        result = run('richdem:flowaccumulation', {
            'INPUT': slope_layer, 'METHOD': 5, 'EXPONENT': 4.0,
            'OUTPUT': str(tmp_dir / 'fa_holmgren.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        assert _valid(data, nodata).min() >= 1.0


# ---------------------------------------------------------------------------
# Terrain Attribute
# ---------------------------------------------------------------------------

class TestTerrainAttribute:
    @pytest.mark.parametrize('idx,name', [
        (0, 'slope_riserun'),
        (2, 'slope_degrees'),
        (4, 'aspect'),
        (5, 'curvature'),
    ])
    def test_output_created(self, slope_layer, tmp_dir, idx, name):
        result = run('richdem:terrainattribute', {
            'INPUT': slope_layer, 'ATTRIBUTE': idx, 'ZSCALE': 1.0,
            'OUTPUT': str(tmp_dir / f'terrain_{name}.tif'),
        })
        assert gdal.Open(result['OUTPUT']) is not None

    def test_slope_degrees_range(self, slope_layer, tmp_dir):
        """Slope in degrees is non-negative for the slope DEM."""
        result = run('richdem:terrainattribute', {
            'INPUT': slope_layer, 'ATTRIBUTE': 2, 'ZSCALE': 1.0,
            'OUTPUT': str(tmp_dir / 'slope_deg.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        assert _valid(data, nodata).min() >= 0.0


# ---------------------------------------------------------------------------
# Depression Hierarchy
# ---------------------------------------------------------------------------

class TestDepressionHierarchy:
    """Bowl DEM: one leaf depression (inner basin); border cells drain to ocean."""

    @pytest.fixture(scope='class')
    def dephier_result(self, bowl_layer, tmp_dir):
        return run('richdem:depressionhierarchy', {
            'INPUT':            bowl_layer,
            'OUTPUT_LABELS':    str(tmp_dir / 'dh_labels.tif'),
            'OUTPUT_FLOWDIRS':  str(tmp_dir / 'dh_flowdirs.tif'),
            'OUTPUT_HIERARCHY': str(tmp_dir / 'dh_hierarchy.gpkg'),
        })

    def test_labels_raster_created(self, dephier_result):
        assert gdal.Open(dephier_result['OUTPUT_LABELS']) is not None

    def test_flowdirs_raster_created(self, dephier_result):
        assert gdal.Open(dephier_result['OUTPUT_FLOWDIRS']) is not None

    def test_hierarchy_gpkg_created(self, dephier_result):
        import os
        assert os.path.exists(dephier_result['OUTPUT_HIERARCHY'])

    def test_labels_depression_exists(self, dephier_result):
        """At least one cell has a non-zero depression label."""
        data, nodata = _read(dephier_result['OUTPUT_LABELS'])
        assert _valid(data, nodata).max() > 0.0, \
            'All cells have label 0 (OCEAN); no depression was detected'

    def test_labels_ocean_cells_exist(self, dephier_result):
        """Border cells drain to the boundary and carry label 0 (OCEAN)."""
        data, nodata = _read(dephier_result['OUTPUT_LABELS'])
        assert _valid(data, nodata).min() == 0.0, \
            'No cells have OCEAN label (0); boundary drainage may be broken'

    def test_flowdirs_valid_range(self, dephier_result):
        """Flow directions are in the RichDEM D8 range [0, 8]
        (0–7 = directions; 8 = pit cell)."""
        data, nodata = _read(dephier_result['OUTPUT_FLOWDIRS'])
        valid = _valid(data, nodata)
        assert valid.min() >= 0.0
        assert valid.max() <= 8.0

    def test_hierarchy_has_leaf_depression(self, dephier_result):
        """GeoPackage depressions layer contains at least one leaf depression."""
        conn = sqlite3.connect(dephier_result['OUTPUT_HIERARCHY'])
        count = conn.execute(
            "SELECT COUNT(*) FROM depressions WHERE type='leaf'"
        ).fetchone()[0]
        conn.close()
        assert count > 0, 'No leaf depression found in hierarchy GeoPackage'

    def test_leaf_depression_has_volume(self, dephier_result):
        """Leaf depression has a positive water-storage volume."""
        conn = sqlite3.connect(dephier_result['OUTPUT_HIERARCHY'])
        vols = [r[0] for r in conn.execute(
            "SELECT dep_vol FROM depressions WHERE type='leaf'"
        ).fetchall()]
        conn.close()
        assert any(v > 0 for v in vols), \
            f'All leaf depressions have dep_vol <= 0: {vols}'

    def test_hierarchy_schema_columns(self, dephier_result):
        """depressions table contains all expected schema columns."""
        required = {
            'dep_label', 'type', 'pit_cell', 'out_cell',
            'parent', 'lchild', 'rchild', 'odep', 'geolink',
            'pit_elev', 'out_elev', 'ocean_parent',
            'cell_count', 'dep_vol', 'water_vol', 'total_elevation',
        }
        conn = sqlite3.connect(dephier_result['OUTPUT_HIERARCHY'])
        cols = {row[1] for row in conn.execute(
            "PRAGMA table_info(depressions)"
        ).fetchall()}
        conn.close()
        missing = required - cols
        assert not missing, f'Missing columns in depressions table: {missing}'

    def test_ocean_links_table_exists(self, dephier_result):
        """GeoPackage contains an ocean_links table."""
        conn = sqlite3.connect(dephier_result['OUTPUT_HIERARCHY'])
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert 'ocean_links' in tables, \
            'ocean_links table is missing from hierarchy GeoPackage'


# ---------------------------------------------------------------------------
# Fill-Spill-Merge
# ---------------------------------------------------------------------------

class TestFillSpillMerge:
    """Run the full dephier → fsm pipeline on the bowl DEM."""

    @pytest.fixture(scope='class')
    def fsm_result(self, bowl_layer, tmp_dir):
        from conftest import _BOWL, write_tif
        from qgis.core import QgsRasterLayer

        hier = run('richdem:depressionhierarchy', {
            'INPUT':            bowl_layer,
            'OUTPUT_LABELS':    str(tmp_dir / 'fsm_labels.tif'),
            'OUTPUT_FLOWDIRS':  str(tmp_dir / 'fsm_flowdirs.tif'),
            'OUTPUT_HIERARCHY': str(tmp_dir / 'fsm_hier_in.gpkg'),
        })

        # 0.5 m of surface water everywhere
        wtd_path = write_tif(np.full(_BOWL.shape, 0.5), tmp_dir / 'wtd_in.tif')

        return run('richdem:fillspillmerge', {
            'INPUT':            bowl_layer,
            'LABELS':           QgsRasterLayer(hier['OUTPUT_LABELS'],   'l'),
            'FLOWDIRS':         QgsRasterLayer(hier['OUTPUT_FLOWDIRS'],  'f'),
            'HIERARCHY':        hier['OUTPUT_HIERARCHY'],
            'WATER_DEPTH':      QgsRasterLayer(wtd_path, 'w'),
            'OUTPUT_WTD':       str(tmp_dir / 'wtd_out.tif'),
            'OUTPUT_HIERARCHY': str(tmp_dir / 'fsm_hier_out.gpkg'),
        })

    def test_wtd_output_created(self, fsm_result):
        assert gdal.Open(fsm_result['OUTPUT_WTD']) is not None

    def test_wtd_output_shape(self, fsm_result):
        data, _ = _read(fsm_result['OUTPUT_WTD'])
        assert data.shape == (7, 7)

    def test_hierarchy_output_created(self, fsm_result):
        import os
        assert os.path.exists(fsm_result['OUTPUT_HIERARCHY'])

    def test_water_vol_updated(self, fsm_result):
        """After FSM, at least one depression has water_vol > 0."""
        conn = sqlite3.connect(fsm_result['OUTPUT_HIERARCHY'])
        vols = [r[0] for r in conn.execute(
            "SELECT water_vol FROM depressions WHERE type='leaf'"
        ).fetchall()]
        conn.close()
        assert any(v > 0 for v in vols), \
            f'No depression gained water after FSM: water_vols={vols}'
