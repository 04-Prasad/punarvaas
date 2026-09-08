# Odisha coastal reference

This derived reference database is made available under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Attribution: **OpenStreetMap contributors; Pathways Data Pvt. Ltd. / lgdirectory.gov.in via geoBoundaries**. These terms cover the reference data, separately from application code.

Retrieved 2026-09-08. The bounded OpenStreetMap extract was downloaded from:
`https://api.openstreetmap.org/api/0.6/map?bbox=86.68,20.52,86.88,20.70`.
Each `relation-<id>.osm` is its complete water/wetland relation from
`https://api.openstreetmap.org/api/0.6/relation/<id>/full`. Raw OSM metadata retains source attribution, versions and timestamps. District outline attribution and download details are in [MAP_BOUNDARIES.md](../../../docs/MAP_BOUNDARIES.md).

`python scripts/prepare_coastal_reference.py` rebuilds the derived files offline:

- `land.geojson`: district intersected with the land side of the OSM coastline, minus mapped water and wetlands. Waterway lines without banks get a 0.00030-degree buffer; water exclusions get another 0.00015 degrees (roughly 15–17 m locally). Whole analysis hexagons must fit within this mask.
- `coastline.geojson`: mapped coastline used for geographic distance; erosion rates remain synthetic.
- `demo-anchors.json`: three mapped settlement points and six representative points of mapped residential polygons. Unnamed clusters retain explicit demo labels. All LGD-format identifiers and demographic/building/facility values are synthetic placeholders, not registry records or observed footprints.

The script uses the OSM [land-left/water-right coastline convention](https://wiki.openstreetmap.org/wiki/Tag:natural%3Dcoastline) and rejects incomplete coastal partitions or missing water-relation geometry. This bounded preparation is for this pilot; a different window needs complete matching reference coverage.

OSM and simplified administrative boundaries can omit features or differ from imagery dates. This is reference land screening, not a current shoreline survey, cadastral clearance, or operational hazard assessment. Keep these reference files with any environment that regenerates the coastal demo.
