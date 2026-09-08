"""Inspect/prepare the bounded OSM reference extract for the synthetic Odisha pilot."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
import argparse
import hashlib
from shapely.geometry import Polygon, LineString, shape, mapping, box
from shapely.ops import polygonize, unary_union
from shapely import make_valid

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data/reference/kendrapara"


def tags(element):
    return {t.get("k"): t.get("v") for t in element.findall("tag")}


def coastline_land(study, coast):
    """Partition this bounded pilot at the OSM coastline (land is on its left).

    Fail closed for incomplete linework; an administrative boundary alone is
    not a shoreline. See https://wiki.openstreetmap.org/wiki/Tag:natural=coastline.
    """
    segments = []
    for line in coast:
        for a, b in zip(line, line[1:]):
            segment = LineString([a, b]).intersection(study)
            if segment.geom_type == 'LineString' and segment.length > 0:
                segments.append(segment)
    pieces = list(polygonize(unary_union([study.boundary, *segments])))
    if not segments or len(pieces) < 2:
        raise ValueError('Coastline does not partition the study extent; check missing ways.')
    kept = []
    for piece in pieces:
        p = piece.representative_point()
        near = min(segments, key=lambda s: s.distance(p))
        a, b = near.coords[0], near.coords[-1]
        if (b[0] - a[0]) * (p.y - a[1]) - (b[1] - a[1]) * (p.x - a[0]) > 0:
            kept.append(piece)
    result = unary_union(kept)
    if result.is_empty or result.area >= study.area:
        raise ValueError('Coastline classification produced no land/sea distinction')
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fetch-relations', action='store_true')
    args = ap.parse_args()
    root = ET.parse(REF / "osm-coastal-reference.osm").getroot()
    relations = [r for r in root.findall('relation') if tags(r).get('natural') in ('water', 'wetland')]
    nodes = {n.get('id'): n for n in root.findall('node')}
    ways = {w.get('id'): w for w in root.findall('way')}
    for relation in relations:
        path = REF / f"relation-{relation.get('id')}.osm"
        if args.fetch_relations and not path.exists():
            url = f"https://api.openstreetmap.org/api/0.6/relation/{relation.get('id')}/full"
            with urlopen(Request(url, headers={'User-Agent': 'Punarvaas-LocalDemo-GeographyFix/1.0'}), timeout=40) as response:
                path.write_bytes(response.read())
        if not path.exists():
            raise RuntimeError(f'Missing full water relation: {path.name}; use --fetch-relations')
        full = ET.parse(path).getroot()
        nodes.update({n.get('id'): n for n in full.findall('node')})
        ways.update({w.get('id'): w for w in full.findall('way')})

    def coordinates(way):
        return [(float(nodes[nd.get('ref')].get('lon')), float(nodes[nd.get('ref')].get('lat'))) for nd in way.findall('nd')]

    excluded, sources = [], []
    water_relation_ways = set()
    for relation in relations:
        rings = {}
        for role in ('outer', 'inner'):
            members = [m.get('ref') for m in relation.findall('member') if m.get('type') == 'way' and (m.get('role') or 'outer') == role]
            if any(m not in ways for m in members):
                raise RuntimeError(f'Incomplete water relation {relation.get("id")}')
            water_relation_ways.update(members)
            lines = [LineString(coordinates(ways[m])) for m in members]
            polygons = list(polygonize(unary_union(lines)))
            if members and not polygons:
                raise RuntimeError(f'Cannot close water relation {relation.get("id")} / {role}')
            rings[role] = unary_union(polygons)
        excluded.append(make_valid(rings['outer'].difference(rings['inner'])))
        sources.append(f"relation/{relation.get('id')}")
    residential = []
    for way in ways.values():
        t = tags(way)
        pts = coordinates(way)
        if len(pts) < 2:
            continue
        closed = len(pts) >= 4 and pts[0] == pts[-1]
        if t.get('landuse') == 'residential' and closed:
            residential.append((way.get('id'), make_valid(Polygon(pts))))
        if t.get('natural') in ('water', 'wetland') or t.get('landuse') == 'reservoir':
            if closed:
                excluded.append(make_valid(Polygon(pts))); sources.append(f"way/{way.get('id')}")
            elif way.get('id') not in water_relation_ways:
                raise RuntimeError(f'Unclosed water boundary {way.get("id")}')
        if t.get('waterway') in ('river', 'stream', 'canal', 'drain'):
            # Reference-only conservative buffer for waterways without mapped banks.
            excluded.append(LineString(pts).buffer(0.00030)); sources.append(f"way/{way.get('id')}")

    state_js = (ROOT / 'web/src/map/state-boundaries.js').read_text(encoding='utf-8')
    contexts = json.loads(state_js.split(' = ', 1)[1].rstrip(';\n'))
    district = make_valid(shape(contexts['kendrapara']['district']['geometry']))
    extent = [86.68, 20.52, 86.88, 20.70]
    study = box(*extent)
    coast = [coordinates(w) for w in ways.values() if tags(w).get('natural') == 'coastline']
    mainland = coastline_land(study, coast)
    water = unary_union(excluded).intersection(study)
    land = make_valid(district.intersection(mainland).difference(water.buffer(0.00015)))
    checksum = hashlib.sha256((REF / 'osm-coastal-reference.osm').read_bytes()).hexdigest()
    metadata = {'bbox': extent, 'retrieved_at': '2026-09-08', 'source': 'OpenStreetMap contributors + geoBoundaries IND ADM2',
                'licence': 'ODbL 1.0', 'osm_extract_sha256': checksum, 'exclusion_sources': sorted(set(sources)),
                'notes': 'District clipped to the land side of OSM coastline, minus mapped water/wetlands; 0.00030-degree waterway buffers and 0.00015-degree exclusion margin. Reference screening, not a current survey.'}
    (REF / 'land.geojson').write_text(json.dumps({'type': 'Feature', 'properties': metadata, 'geometry': mapping(land)}, separators=(',', ':')) + '\n')
    (REF / 'coastline.geojson').write_text(json.dumps({'type': 'Feature', 'properties': metadata,
        'geometry': {'type': 'MultiLineString', 'coordinates': coast}}, separators=(',', ':')) + '\n')
    anchors = []
    for node in root.findall('node'):
        t = tags(node)
        if t.get('place') not in ('village', 'hamlet'):
            continue
        point = shape({'type': 'Point', 'coordinates': [float(node.get('lon')), float(node.get('lat'))]})
        if land.covers(point):
            anchors.append({'name': t.get('name', 'Unnamed mapped settlement'), 'lon': point.x, 'lat': point.y,
                            'osm': f"node/{node.get('id')}", 'is_town': t.get('name') == 'Rajnagar'})
    for oid, polygon in residential:
        usable = polygon.intersection(land)
        if not usable.is_empty:
            point = usable.representative_point()
            anchors.append({'name': f'Coastal demo cluster {len(anchors) + 1:02d}', 'lon': point.x, 'lat': point.y,
                            'osm': f'way/{oid}', 'is_town': False})
    for i, anchor in enumerate(anchors):
        anchor['lgd_village_code'] = f'379{i + 1:03d}'
        anchor['is_synthetic'] = True
    (REF / 'demo-anchors.json').write_text(json.dumps({'metadata': metadata, 'anchors': anchors}, indent=2) + '\n')
    print(json.dumps(anchors, indent=2))
    print(f'Land mask: {(REF / "land.geojson").stat().st_size:,} bytes; {len(sources)} water/wetland references')


if __name__ == "__main__":
    main()
