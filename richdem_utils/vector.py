"""Conversion between RichDEM depression hierarchy objects and GeoPackage files."""

import math
import os
import shutil
import sqlite3
import tempfile
from collections import defaultdict

import numpy as np
from osgeo import gdal, ogr, osr

# std::numeric_limits<uint32_t>::max() — NO_VALUE / NO_PARENT sentinel
_NO_VALUE = 2**32 - 1


def _flat_to_xy(flat_idx, cols, gt):
    """Convert a flat cell index to projected x, y coordinates (cell centre)."""
    row, col = divmod(int(flat_idx), cols)
    x = gt[0] + (col + 0.5) * gt[1]
    y = gt[3] + (row + 0.5) * gt[5]  # gt[5] is negative
    return x, y


def _is_no_value(v):
    return int(v) == _NO_VALUE


def _make_field(name, otype):
    return ogr.FieldDefn(name, otype)


_FIELD_DEFS = [
    ('type',            ogr.OFTString),
    ('pit_cell',        ogr.OFTInteger64),
    ('out_cell',        ogr.OFTInteger64),
    ('parent',          ogr.OFTInteger64),
    ('odep',            ogr.OFTInteger64),
    ('lchild',          ogr.OFTInteger64),
    ('rchild',          ogr.OFTInteger64),
    ('geolink',         ogr.OFTInteger64),
    ('pit_elev',        ogr.OFTReal),
    ('out_elev',        ogr.OFTReal),
    ('ocean_parent',    ogr.OFTInteger),
    ('cell_count',      ogr.OFTInteger64),
    ('dep_vol',         ogr.OFTReal),
    ('water_vol',       ogr.OFTReal),
    ('total_elevation', ogr.OFTReal),
]


def _set_dep_fields(feat, d):
    is_leaf = _is_no_value(d.lchild)
    feat.SetField('type', 'leaf' if is_leaf else 'meta')
    feat.SetField('pit_cell', int(d.pit_cell))
    feat.SetField('out_cell', int(d.out_cell))
    for attr in ('parent', 'odep', 'lchild', 'rchild', 'geolink'):
        v = int(getattr(d, attr))
        feat.SetField(attr, None if _is_no_value(v) else v)
    for attr in ('pit_elev', 'out_elev'):
        f = float(getattr(d, attr))
        feat.SetField(attr, None if (math.isinf(f) or math.isnan(f)) else f)
    feat.SetField('ocean_parent', int(bool(d.ocean_parent)))
    feat.SetField('cell_count', int(d.cell_count))
    feat.SetField('dep_vol', float(d.dep_vol))
    feat.SetField('water_vol', float(d.water_vol))
    feat.SetField('total_elevation', float(d.total_elevation))


def depressions_to_gpkg(deps, labels, output_path):
    """Write a RichDEM depression hierarchy to a GeoPackage.

    Layer 'depressions': polygon per leaf depression + point per metadepression.
    Layer 'ocean_links': non-spatial attribute table for ocean_linked relationships.
    """
    from _richdem.depression_hierarchy import OCEAN

    OCEAN_val = int(OCEAN)
    rows, cols = labels.shape
    gt = labels.geotransform
    projection = getattr(labels, '_projection', '')

    # --- Step 1: write labels to a temporary GeoTIFF for Polygonize ---
    tmp_path = output_path + '.tmp_labels.tif'
    tif_driver = gdal.GetDriverByName('GTiff')
    tmp_ds = tif_driver.Create(tmp_path, cols, rows, 1, gdal.GDT_Int32)
    tmp_ds.SetGeoTransform(gt)
    if projection:
        tmp_ds.SetProjection(projection)
    label_data = np.array(labels, dtype=np.int32)
    label_data[label_data == OCEAN_val] = -1  # OCEAN → nodata so Polygonize skips it
    band = tmp_ds.GetRasterBand(1)
    band.WriteArray(label_data)
    band.SetNoDataValue(-1)
    tmp_ds.FlushCache()

    # --- Step 2: create GeoPackage and polygonize labels → leaf depression areas ---
    gpkg_driver = ogr.GetDriverByName('GPKG')
    if os.path.exists(output_path):
        gpkg_driver.DeleteDataSource(output_path)
    gpkg_ds = gpkg_driver.CreateDataSource(output_path)

    srs = osr.SpatialReference()
    if projection:
        srs.ImportFromWkt(projection)

    # wkbUnknown: layer will hold both Polygon (leaves) and Point (metas)
    dep_layer = gpkg_ds.CreateLayer('depressions', srs=srs, geom_type=ogr.wkbUnknown)
    dep_layer.CreateField(ogr.FieldDefn('dep_label', ogr.OFTInteger))
    for name, otype in _FIELD_DEFS:
        dep_layer.CreateField(ogr.FieldDefn(name, otype))

    # GetMaskBand() returns 0 for nodata pixels (-1), 255 for all others
    gdal.Polygonize(band, band.GetMaskBand(), dep_layer, 0)

    tmp_ds = None
    try:
        os.unlink(tmp_path)
    except OSError:
        pass

    # --- Step 3: populate leaf depression attributes ---
    dep_by_label = {
        int(d.dep_label): d
        for d in deps
        if int(d.dep_label) != OCEAN_val and _is_no_value(d.lchild)
    }
    dep_layer.ResetReading()
    for feat in dep_layer:
        lbl = feat.GetField('dep_label')
        d = dep_by_label.get(lbl)
        if d is not None:
            _set_dep_fields(feat, d)
            dep_layer.SetFeature(feat)

    # --- Step 4: add metadepression point geometries + attributes ---
    meta_deps = [
        d for d in deps
        if int(d.dep_label) != OCEAN_val and not _is_no_value(d.lchild)
    ]
    layer_defn = dep_layer.GetLayerDefn()
    for d in meta_deps:
        x, y = _flat_to_xy(d.out_cell, cols, gt)
        feat = ogr.Feature(layer_defn)
        feat.SetGeometry(ogr.CreateGeometryFromWkt(f'POINT ({x} {y})'))
        feat.SetField('dep_label', int(d.dep_label))
        _set_dep_fields(feat, d)
        dep_layer.CreateFeature(feat)

    # --- Step 5: ocean_links as a non-spatial attribute table ---
    links_layer = gpkg_ds.CreateLayer('ocean_links', geom_type=ogr.wkbNone)
    links_layer.CreateField(ogr.FieldDefn('dep_label', ogr.OFTInteger))
    links_layer.CreateField(ogr.FieldDefn('linked_label', ogr.OFTInteger))
    links_defn = links_layer.GetLayerDefn()
    for d in deps:
        for lnk in d.ocean_linked:
            feat = ogr.Feature(links_defn)
            feat.SetField('dep_label', int(d.dep_label))
            feat.SetField('linked_label', int(lnk))
            links_layer.CreateFeature(feat)

    gpkg_ds = None


def depressions_from_gpkg(gpkg_path):
    """Read a GeoPackage depression hierarchy back into a Depression list.

    The returned list is indexed by depression label (deps[label] == that
    depression).  deps[0] is always the synthetic OCEAN pseudo-depression
    required by FillSpillMerge's internal indexing.
    """
    from _richdem.depression_hierarchy import Depression, OCEAN

    conn = sqlite3.connect(gpkg_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT dep_label, pit_cell, out_cell, parent, odep, lchild, rchild,
               geolink, pit_elev, out_elev, ocean_parent, cell_count,
               dep_vol, water_vol, total_elevation
        FROM depressions
        GROUP BY dep_label
        ORDER BY dep_label
    """)
    rows = cur.fetchall()

    cur.execute("SELECT dep_label, linked_label FROM ocean_links ORDER BY dep_label")
    ocean_linked = defaultdict(list)
    for dep_label, linked_label in cur.fetchall():
        ocean_linked[dep_label].append(linked_label)

    conn.close()

    def restore_int(val):
        return _NO_VALUE if val is None else int(val)

    def restore_float(val):
        return float('inf') if val is None else float(val)

    # Determine the size of the deps vector (max label + 1).
    if rows:
        max_label = max(int(r[0]) for r in rows)
    else:
        max_label = 0

    # Pre-allocate with default Depressions; deps[0] is the OCEAN sentinel.
    ocean = Depression()
    ocean.dep_label = int(OCEAN)  # 0
    # The ocean_links table stores which real depressions overflow into OCEAN.
    ocean.ocean_linked = ocean_linked.get(int(OCEAN), [])
    deps = [ocean] + [Depression() for _ in range(max_label)]

    for row in rows:
        (dep_label, pit_cell, out_cell, parent, odep, lchild, rchild,
         geolink, pit_elev, out_elev, ocean_parent, cell_count,
         dep_vol, water_vol, total_elevation) = row

        idx = int(dep_label)
        d = deps[idx]
        d.dep_label       = idx
        d.pit_cell        = int(pit_cell)
        d.out_cell        = int(out_cell)
        d.parent          = restore_int(parent)
        d.odep            = restore_int(odep)
        d.lchild          = restore_int(lchild)
        d.rchild          = restore_int(rchild)
        d.geolink         = restore_int(geolink)
        d.pit_elev        = restore_float(pit_elev)
        d.out_elev        = restore_float(out_elev)
        d.ocean_parent    = bool(ocean_parent)
        d.cell_count      = int(cell_count)
        d.dep_vol         = float(dep_vol)
        d.water_vol       = float(water_vol)
        d.total_elevation = float(total_elevation)
        d.ocean_linked    = ocean_linked.get(dep_label, [])

    return deps


def update_water_vol(deps, gpkg_path):
    """Write updated water_vol values from a Depression list back to the GeoPackage.

    Uses OGR (not raw sqlite3) so that GDAL's registered ST_ functions are
    available to the GeoPackage geometry triggers on the depressions table.
    """
    from osgeo import ogr
    ds = ogr.Open(gpkg_path, 1)   # 1 = update mode
    if ds is None:
        raise RuntimeError(f'Cannot open GeoPackage for update: {gpkg_path}')
    layer = ds.GetLayerByName('depressions')
    water_vols = {d.dep_label: d.water_vol for d in deps}
    layer.ResetReading()
    feature = layer.GetNextFeature()
    while feature is not None:
        label = feature.GetField('dep_label')
        if label in water_vols:
            feature.SetField('water_vol', water_vols[label])
            layer.SetFeature(feature)
        feature = layer.GetNextFeature()
    ds = None
