# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.1.0] - 2026-05-29

### Added

- **Fill Depressions** — Priority-Flood algorithm (Barnes 2014); D8/D4 topology; optional epsilon gradient for drainable output
- **Breach Depressions** — least-cost breaching (Lindsay 2016 / Barnes 2016); D8/D4 topology; optional epsilon variant (D8 only)
- **Resolve Flats** — gradient imposition on flat regions after filling or breaching (Barnes 2014)
- **Flow Accumulation** — upstream contributing area via 13 flow-routing methods (D8, D4, Dinf/Tarboton, Quinn, Holmgren, Freeman, Rho8/Rho4, FairfieldLeymarie D8/D4, OCallaghan D8/D4)
- **Terrain Attribute** — slope (rise/run, %, °, radians), aspect, curvature, planform curvature, profile curvature; optional vertical exaggeration
- **Depression Hierarchy** — nested depression tree (Barnes 2020); GeoPackage output with polygon/point geometries and full attribute table
- **Fill-Spill-Merge** — surface-water distribution across depression hierarchies (Barnes 2020); accepts a water-depth raster or a uniform scalar; zero-depth shortcut skips computation
