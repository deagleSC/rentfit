# 2. Localities as Voronoi cells around OpenStreetMap suburbs

**Status:** accepted (Phase 0)

## Context
Search, pins and rent fallbacks need named areas with polygons. OSM admin boundaries in Bengaluru
and Mumbai are inconsistent (missing, overlapping, at mixed levels).

## Decision
Use OSM `place=suburb` points (plus a curated list of rental areas), build Voronoi cells around
them, and clip each to 3 km. Pin → locality uses `st_covers`, else the nearest cell within 500 m.
Locality notes are written by template from OSM counts (no model).

## Consequences
- Every point in a city maps to exactly one named area; names match what people say.
- Cells do not follow real ward lines and are not clipped to land, so a coastal pin can sit on
  the shoreline (seen on the Mumbai map). Clipping to the coastline is a follow-up.
- Kolkata was dropped: Overpass could not return its data reliably.
