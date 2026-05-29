# RichDEM Terrain Analysis — QGIS Processing Plugin

A QGIS Processing provider that exposes seven terrain-analysis algorithms from the
[RichDEM](https://richdem.com) library, including hydrological conditioning,
flow routing, surface-water distribution (Fill-Spill-Merge), and standard terrain
attributes.

## Algorithms

| Algorithm | Description |
|-----------|-------------|
| **Fill Depressions** | Priority-Flood depression filling (Barnes 2014). Optional epsilon gradient ensures drainable output. D8 or D4 topology. |
| **Breach Depressions** | Least-cost depression breaching (Lindsay 2016 / Barnes 2016). Cuts channels rather than filling; better preserves terrain morphology. Optional epsilon variant (D8 only). |
| **Resolve Flats** | Adds a small gradient to flat regions left after filling or breaching so that flow can be routed through them (Barnes 2014). |
| **Flow Accumulation** | Upstream contributing area using any of 13 flow-routing methods: D8, D4, Dinf/Tarboton, Quinn, Holmgren, Freeman, Rho8/Rho4, FairfieldLeymarie (D8/D4), and OCallaghan (D8/D4). |
| **Terrain Attribute** | Slope (rise/run, %, °, radians), aspect, curvature, planform curvature, and profile curvature. Optional vertical exaggeration scale factor. |
| **Depression Hierarchy** | Constructs a RichDEM depression hierarchy (Barnes 2020): a tree of nested depressions with overflow connections. Output is a GeoPackage with polygon/point geometries and a full attribute table. Required input for Fill-Spill-Merge. |
| **Fill-Spill-Merge** | Distributes a given water depth across a DEM, accounting for depression filling, spilling between basins, and merging of flooded areas (Barnes 2020). Accepts a water-depth raster or a uniform scalar depth. |

## Requirements

### QGIS

QGIS 3.16 or later.

### RichDEM Python bindings

The `richdem` Python package must be installed in the Python environment that QGIS uses.

**Linux / macOS (system Python or OSGeo4W):**
```bash
pip install richdem
```

**Windows (OSGeo4W shell):**
```bat
pip install richdem
```

The plugin raises an informative error at run time if `richdem` is not found — it does
not silently fail.

## Installation

1. Download or clone this repository.
2. Copy (or symlink) the `processing_richdem` folder into your QGIS plugins directory:
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
3. Restart QGIS, open *Plugins → Manage and Install Plugins*, and enable
   **RichDEM Terrain Analysis**.
4. All seven algorithms appear under **Processing → Toolbox → RichDEM → Hydrology**.

## Running the tests

Tests require `pytest`, `numpy`, `richdem`, and GDAL/osgeo (from QGIS or standalone).
They do **not** require a running QGIS instance.

```bash
pip install pytest
pytest tests/
```

The test suite uses a small synthetic DEM (a pit–saddle–ring design) and covers all
seven algorithms including edge cases (epsilon breaching, scalar water depth, zero-water
bypass, schema validation of the depression hierarchy GeoPackage).

## Background and references

Barnes, R. (2014). Priority-Flood: An Optimal Depression-Filling and Watershed-Labeling
Algorithm for Digital Elevation Models. *Computers & Geosciences*, 62, 117–127.

Barnes, R., Lehman, C., & Mulla, D. (2014). An efficient assignment of drainage direction
over flat surfaces in raster digital elevation models. *Computers & Geosciences*, 62, 128–135.

Lindsay, J. B. (2016). Efficient hybrid breaching-filling sink removal methods for flow path
enforcement in digital elevation models. *Hydrological Processes*, 30(6), 846–857.

Barnes, R., Callaghan, K., & Wickert, A. D. (2020). Computing water flow through complex
landscapes, Part 2: Finding hierarchies in depressions and morphological units.
*Earth Surface Dynamics*, 8, 431–445.

Barnes, R., Callaghan, K., & Wickert, A. D. (2020). Computing water flow through complex
landscapes, Part 3: Fill-Spill-Merge — surface water flow in depression hierarchies.
*Earth Surface Dynamics*, 9, 105–121.

## License

GPL-3.0. See [LICENSE](LICENSE). This license matches RichDEM, which is linked at
runtime.
