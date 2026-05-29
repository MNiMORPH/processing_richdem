"""End-to-end tests for all seven Processing algorithms via processing.run().

Mirrors the assertions in the r.richdem GRASS testsuite, adapted for QGIS
and GeoPackage outputs.
"""

import sqlite3

import numpy as np
import pytest
from osgeo import gdal

try:
    import _richdem as _rd_ext
    HAS_RICHDEM = True
    HAS_LINDSAY2016 = hasattr(_rd_ext, 'rdBreachDepressionsEpsD8')
except ImportError:
    HAS_RICHDEM = False
    HAS_LINDSAY2016 = False


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
    """Bowl DEM: outer region=5, ring=9, pit=1, saddle=4.
    Pour-point = 5 (border); fill raises pit and saddle to 5, ring (9) unchanged."""

    def test_output_created(self, bowl_layer, tmp_dir):
        """Filling a depressed DEM produces an output raster."""
        result = run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': False,
            'OUTPUT': str(tmp_dir / 'filled.tif'),
        })
        assert gdal.Open(result['OUTPUT']) is not None

    def test_pit_raised_to_pour_point(self, bowl_layer, tmp_dir):
        """Pit and saddle rise to pour-point (5); ring (9) is unchanged."""
        result = run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': False,
            'OUTPUT': str(tmp_dir / 'filled2.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        valid = _valid(data, nodata)
        assert valid.min() == pytest.approx(5.0)
        assert valid.max() == pytest.approx(9.0)

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

    def test_epsilon_flag_preserves_range(self, bowl_layer, tmp_dir):
        """With epsilon, min stays at pour-point (5) and max stays at ring (9)."""
        result = run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': True,
            'OUTPUT': str(tmp_dir / 'filled_eps.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        valid = _valid(data, nodata)
        assert valid.min() >= 5.0
        assert valid.max() == pytest.approx(9.0)

    def test_d4_topology(self, bowl_layer, tmp_dir):
        """D4 topology raises pit and saddle to pour-point (5); ring (9) unchanged."""
        result = run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 1, 'EPSILON': False,
            'OUTPUT': str(tmp_dir / 'filled_d4.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        valid = _valid(data, nodata)
        assert valid.min() == pytest.approx(5.0)
        assert valid.max() == pytest.approx(9.0)


# ---------------------------------------------------------------------------
# Breach Depressions
# ---------------------------------------------------------------------------

class TestBreachDepressions:
    """Bowl DEM: pit=1, saddle=4, ring=9, outer=5.
    CompleteBreaching raises pit to saddle (4); fill raises to pour-point (5)."""

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

    def test_pit_raised_to_saddle(self, bowl_layer, tmp_dir):
        """CompleteBreaching raises pit to saddle (4); ring (9) is unchanged."""
        result = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0,
            'OUTPUT': str(tmp_dir / 'breached3.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        valid = _valid(data, nodata)
        assert valid.min() == pytest.approx(4.0)
        assert valid.max() == pytest.approx(9.0)

    def test_breach_below_pour_point(self, bowl_layer, tmp_dir):
        """Breach min (4.0) is strictly below the fill pour-point (5.0).

        Fill raises both pit and saddle to the border elevation (5); breach
        raises the pit only to the saddle elevation (4), preserving the saddle.
        """
        result = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0,
            'OUTPUT': str(tmp_dir / 'breached4.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        assert _valid(data, nodata).min() < 5.0, \
            'min of breached DEM >= 5.0; pit was raised to pour-point (fill behaviour)'

    def test_d4_topology(self, bowl_layer, tmp_dir):
        """D4 topology raises pit to saddle (4); ring (9) unchanged."""
        result = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 1,
            'OUTPUT': str(tmp_dir / 'breached_d4.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        valid = _valid(data, nodata)
        assert valid.min() == pytest.approx(4.0)
        assert valid.max() == pytest.approx(9.0)


# ---------------------------------------------------------------------------
# Breach Depressions — epsilon variant
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not HAS_LINDSAY2016,
    reason='rdBreachDepressionsEpsD8 not available in this RichDEM build',
)
class TestBreachDepressionsEps:
    """Lindsay2016 epsilon-gradient breaching: pit shallowed to just below saddle.

    Bowl DEM: pit=1, saddle=4, ring=9, outer=5.
    BreachDepressionsEps uses std::nextafter to raise the pit to
    nextafter(4.0, -inf) ≈ 3.9999…, strictly below the saddle elevation.
    This gives a binary min < 4.0, distinguishing it from CompleteBreaching
    (min == 4.0) and fill (min == 5.0).
    """

    def test_output_created(self, bowl_layer, tmp_dir):
        """Epsilon breaching produces an output raster."""
        result = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': True,
            'OUTPUT': str(tmp_dir / 'breached_eps.tif'),
        })
        assert gdal.Open(result['OUTPUT']) is not None

    def test_epsilon_shallows_below_saddle(self, bowl_layer, tmp_dir):
        """Pit is raised to nextafter(4.0, -inf); binary min < 4.0.

        Unlike CompleteBreaching (min == 4.0), epsilon-gradient breaching
        uses std::nextafter so the pit elevation is strictly below the saddle.
        The difference from 4.0 is ~1 ULP (~1.8e-15), so we compare the
        raw numpy float64 array rather than relying on text output.
        """
        result = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': True,
            'OUTPUT': str(tmp_dir / 'breached_eps2.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        valid = _valid(data, nodata)
        assert valid.min() < 4.0, \
            'binary min of eps-breached DEM >= 4.0; pit was not shallowed below saddle'

    def test_eps_below_complete_breach(self, bowl_layer, tmp_dir):
        """Epsilon min is strictly less than CompleteBreaching min (4.0)."""
        result_eps = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': True,
            'OUTPUT': str(tmp_dir / 'breached_eps3.tif'),
        })
        result_std = run('richdem:breachdepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': False,
            'OUTPUT': str(tmp_dir / 'breached_std3.tif'),
        })
        eps_min = _valid(*_read(result_eps['OUTPUT'])).min()
        std_min = _valid(*_read(result_std['OUTPUT'])).min()
        assert eps_min < std_min, \
            f'eps min ({eps_min}) not less than standard min ({std_min})'


# ---------------------------------------------------------------------------
# Resolve Flats
# ---------------------------------------------------------------------------

class TestResolveFlats:
    """Bowl DEM filled to pour-point (min=5, max=9), then flats resolved.

    After filling, the outer region and former pit/saddle form a flat at 5.
    ResolveFlats imposes a tiny gradient so all cells drain unambiguously;
    no values should be introduced below the fill pour-point (5) or above
    the ring elevation (9).
    """

    @pytest.fixture(scope='class')
    def resolved_result(self, bowl_layer, tmp_dir):
        from qgis.core import QgsRasterLayer
        filled_path = str(tmp_dir / 'rf_filled.tif')
        run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 0, 'EPSILON': False,
            'OUTPUT': filled_path,
        })
        return run('richdem:resolveflats', {
            'INPUT': QgsRasterLayer(filled_path, 'f'),
            'OUTPUT': str(tmp_dir / 'resolved.tif'),
        })

    def test_output_created(self, resolved_result):
        """ResolveFlats on a pre-filled DEM produces output."""
        assert gdal.Open(resolved_result['OUTPUT']) is not None

    def test_no_nulls_introduced(self, resolved_result):
        """ResolveFlats does not introduce nodata/NaN cells."""
        data, nodata = _read(resolved_result['OUTPUT'])
        valid = _valid(data, nodata)
        assert len(valid) == data.size, \
            'ResolveFlats introduced null cells'

    def test_min_max_preserved(self, resolved_result):
        """After resolving flats, min stays at pour-point (≥5) and max at ring (9)."""
        data, nodata = _read(resolved_result['OUTPUT'])
        valid = _valid(data, nodata)
        assert valid.min() >= 5.0, \
            'ResolveFlats lowered a cell below the fill pour-point (5)'
        assert valid.max() == pytest.approx(9.0), \
            'ResolveFlats changed the ring elevation (9)'

    def test_d4_topology(self, bowl_layer, tmp_dir):
        """D4-filled DEM resolves flats without error; range preserved."""
        from qgis.core import QgsRasterLayer
        filled_path = str(tmp_dir / 'rf_filled_d4.tif')
        run('richdem:filldepressions', {
            'INPUT': bowl_layer, 'TOPOLOGY': 1, 'EPSILON': False,
            'OUTPUT': filled_path,
        })
        result = run('richdem:resolveflats', {
            'INPUT': QgsRasterLayer(filled_path, 'f'),
            'OUTPUT': str(tmp_dir / 'resolved_d4.tif'),
        })
        data, nodata = _read(result['OUTPUT'])
        valid = _valid(data, nodata)
        assert valid.min() >= 5.0
        assert valid.max() == pytest.approx(9.0)


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
            'fid',
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
