"""Generate interactive maps from IGC flight tracks"""

import logging
from pathlib import Path
from typing import List, Tuple, Optional
import random
import json
import subprocess
import sys

logger = logging.getLogger(__name__)

try:
    import folium
    from folium import plugins
    from folium.plugins import HeatMap
except ImportError as e:
    logger.error(f"Missing dependencies for map generation: {e}")
    logger.error("Install with: pip install folium")
    raise


class FlightTrack:
    """Represents a single flight track"""

    def __init__(
        self,
        filename: str,
        coordinates: List[Tuple[float, float]],
        flight_date: str = None,
        aircraft: str = None,
        duration: str = None,
        points: float = None,
        flight_id: str = None,
        dsid: str = None,
        distance_km: float = None,
        avg_speed_kmh: float = None,
        max_speed_kmh: float = None,
        task: dict = None,
    ):
        self.filename = filename
        self.coordinates = coordinates
        self.pilot_name = self._extract_pilot_name(filename)
        self.pilot_display_name = self._clean_pilot_name(self.pilot_name)
        self.year = self._extract_year(filename)
        self.flight_date = flight_date or self.year
        self.aircraft = aircraft or "Unknown"
        self.duration = duration
        self.points = points
        self.flight_id = flight_id
        self.dsid = dsid
        self.distance_km = distance_km
        self.avg_speed_kmh = avg_speed_kmh
        self.max_speed_kmh = max_speed_kmh
        self.task = task  # Task declaration from C records

    def _extract_pilot_name(self, filename: str) -> str:
        """Extract pilot name from filename (format: YEAR_PILOT_FLIGHTID.igc)"""
        parts = Path(filename).stem.split('_')
        if len(parts) >= 3:
            # Join all parts between year and flight ID
            return '_'.join(parts[1:-1])
        return "Unknown"

    def _clean_pilot_name(self, pilot_name: str) -> str:
        """
        Clean up pilot name for display:
        - Remove underscores
        - Remove region codes like (US_-_R1), (BE), etc.
        """
        # Remove region codes in parentheses
        import re
        cleaned = re.sub(r'\s*\([^)]*\)', '', pilot_name)
        # Replace underscores with spaces
        cleaned = cleaned.replace('_', ' ')
        return cleaned.strip()

    def _extract_year(self, filename: str) -> str:
        """Extract year from filename (format: YEAR_PILOT_FLIGHTID.igc)"""
        parts = Path(filename).stem.split('_')
        if len(parts) >= 3:
            return parts[0]
        return "Unknown"


class MapGenerator:
    """Generates interactive maps from IGC files"""

    # US boundaries (lat_min, lat_max, lon_min, lon_max)
    # Mainland: Northern border at 49°N (US-Canada border), southern tip of Florida/Texas
    US_MAINLAND = (24.5, 49.0, -125.0, -66.0)
    # Alaska: Aleutian Islands to northern Arctic coast
    US_ALASKA = (51.0, 71.5, -179.0, -130.0)
    # Hawaii: All Hawaiian islands
    US_HAWAII = (18.9, 28.5, -178.0, -154.0)

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)

    def export_flight_data(
        self,
        tracks: List[FlightTrack],
        output_dir: Path,
        deployment_mode: str = 'local'
    ) -> Tuple[Path, List[dict]]:
        """
        Export flight track data to separate JSON files for dynamic loading.

        Args:
            tracks: List of FlightTrack objects
            output_dir: Directory to save flight data files
            deployment_mode: Deployment mode - 'local' or 'static'

        Returns:
            Tuple of (manifest_path, list of flight metadata dicts)
        """
        flights_dir = output_dir / "flights"
        flights_dir.mkdir(parents=True, exist_ok=True)

        flight_metadata_list = []

        logger.info(f"Exporting {len(tracks)} flights to separate JSON files...")

        for i, track in enumerate(tracks):
            # Generate unique flight ID
            flight_id = f"flight_{i:04d}"

            # Create flight data file
            flight_data = {
                "id": flight_id,
                "coordinates": track.coordinates,
                "pilot_name": track.pilot_name,
                "pilot_display_name": track.pilot_display_name,
                "year": track.year,
                "flight_date": track.flight_date,
                "aircraft": track.aircraft,
                "duration": track.duration,
                "distance_km": track.distance_km,
                "avg_speed_kmh": track.avg_speed_kmh,
                "points": track.points,
                "filename": track.filename,
                "dsid": track.dsid
            }

            # Save individual flight data
            flight_file = flights_dir / f"{flight_id}.json"
            with open(flight_file, 'w') as f:
                json.dump(flight_data, f, separators=(',', ':'))  # Compact JSON

            # Create metadata entry (no coordinates - keep manifest small)
            metadata = {
                "id": flight_id,
                "file": f"flights/{flight_id}.json",
                "pilot_name": track.pilot_name,
                "pilot_display_name": track.pilot_display_name,
                "year": track.year,
                "flight_date": track.flight_date,
                "aircraft": track.aircraft,
                "duration": track.duration,
                "distance_km": track.distance_km,
                "avg_speed_kmh": track.avg_speed_kmh,
                "points": track.points,
                "filename": track.filename,
                "dsid": track.dsid,
                "color_index": i  # For consistent coloring
            }

            flight_metadata_list.append(metadata)

        # Create manifest file
        manifest_path = output_dir / "flights_manifest.json"
        manifest = {
            "total_flights": len(tracks),
            "deployment_mode": deployment_mode,
            "flights": flight_metadata_list
        }

        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"Exported flight data:")
        logger.info(f"  - {len(tracks)} flight JSON files in {flights_dir}")
        logger.info(f"  - Manifest: {manifest_path}")

        # Calculate size savings
        manifest_size_mb = manifest_path.stat().st_size / (1024 * 1024)
        total_flight_files_size_mb = sum((flights_dir / f"{f['id']}.json").stat().st_size
                                          for f in flight_metadata_list) / (1024 * 1024)
        logger.info(f"  - Manifest size: {manifest_size_mb:.2f} MB")
        logger.info(f"  - Total flight files: {total_flight_files_size_mb:.2f} MB")

        return manifest_path, flight_metadata_list

    def export_waypoint_data(
        self,
        waypoints: List[dict],
        output_dir: Path
    ) -> Path:
        """
        Export waypoint data to separate JSON file for on-demand popup loading.

        Args:
            waypoints: List of waypoint dicts
            output_dir: Directory to save waypoint data

        Returns:
            Path to waypoints JSON file
        """
        waypoints_path = output_dir / "waypoints.json"

        # Icon configuration (matches inline version)
        icon_config = {
            'airport': {'color': '#E53E3E', 'icon': '✈️', 'type_label': 'Airport'},
            'turnpoint': {'color': '#38A169', 'icon': '🎯', 'type_label': 'Turnpoint'},
            'landmark': {'color': '#718096', 'icon': '🏔️', 'type_label': 'Landmark'},
            'other': {'color': '#3182CE', 'icon': '📍', 'type_label': 'Waypoint'}
        }

        waypoint_data = []
        for idx, wp in enumerate(waypoints):
            wp_type = wp.get('type', 'other')
            config = icon_config.get(wp_type, icon_config['other'])

            waypoint_data.append({
                'id': f'waypoint_{idx}',
                'name': wp['name'],
                'lat': wp['lat'],
                'lon': wp['lon'],
                'description': wp.get('description', 'No additional information'),
                'type': wp_type,
                'color': config['color'],
                'icon': config['icon'],
                'type_label': config['type_label']
            })

        with open(waypoints_path, 'w') as f:
            json.dump({'waypoints': waypoint_data}, f, indent=2)

        logger.info(f"Exported {len(waypoints)} waypoints to {waypoints_path}")
        waypoints_size_kb = waypoints_path.stat().st_size / 1024
        logger.info(f"  - Size: {waypoints_size_kb:.1f} KB")

        return waypoints_path

    def export_heatmap_data(
        self,
        heatmap_data: List[List[float]],
        output_dir: Path
    ) -> Path:
        """
        Export heatmap data to separate JSON file for on-demand loading.

        Args:
            heatmap_data: List of [lat, lon] coordinate pairs
            output_dir: Directory to save heatmap data

        Returns:
            Path to heatmap JSON file
        """
        heatmap_path = output_dir / "heatmap.json"

        with open(heatmap_path, 'w') as f:
            json.dump({'coordinates': heatmap_data}, f, separators=(',', ':'))  # Compact JSON

        logger.info(f"Exported {len(heatmap_data)} heatmap coordinates to {heatmap_path}")
        heatmap_size_mb = heatmap_path.stat().st_size / (1024 * 1024)
        logger.info(f"  - Size: {heatmap_size_mb:.1f} MB")

        return heatmap_path

    def is_in_us(self, lat: float, lon: float) -> bool:
        """
        Check if a coordinate is within US boundaries

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            True if coordinate is within US boundaries (mainland, Alaska, or Hawaii)
        """
        # Check mainland US
        lat_min, lat_max, lon_min, lon_max = self.US_MAINLAND
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True

        # Check Alaska
        lat_min, lat_max, lon_min, lon_max = self.US_ALASKA
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True

        # Check Hawaii
        lat_min, lat_max, lon_min, lon_max = self.US_HAWAII
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True

        return False

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points on Earth in kilometers

        Args:
            lat1, lon1: First point in decimal degrees
            lat2, lon2: Second point in decimal degrees

        Returns:
            Distance in kilometers
        """
        import math

        # Convert to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in kilometers
        r = 6371

        return c * r

    def _parse_task_from_c_records(self, c_records: List[str]) -> Optional[dict]:
        """
        Parse task declaration from IGC C records

        C record format:
        - First C record: Task header with date/time
        - Subsequent C records: C<lat><lon><name>
          Example: C4814183N12201383WEBEY HILL
                   = 48°14.183'N, 122°01.383'W, name: WEBEY HILL

        Returns:
            dict with turnpoints list or None if parsing fails
        """
        if not c_records or len(c_records) < 2:
            return None

        turnpoints = []

        for record in c_records[1:]:  # Skip header record
            try:
                # C record format: C DDMMmmmN/S DDDMMmmmE/W NAME
                if len(record) < 19:  # Minimum length for C record with coordinates
                    continue

                # Extract latitude (positions 1-7: DDMMmmm, position 8: N/S)
                lat_deg = int(record[1:3])
                lat_min = float(record[3:8]) / 1000.0
                lat_dir = record[8]
                lat = lat_deg + lat_min / 60.0
                if lat_dir == 'S':
                    lat = -lat

                # Extract longitude (positions 9-16: DDDMMmmm, position 17: E/W)
                lon_deg = int(record[9:12])
                lon_min = float(record[12:17]) / 1000.0
                lon_dir = record[17]
                lon = lon_deg + lon_min / 60.0
                if lon_dir == 'W':
                    lon = -lon

                # Extract name (everything after position 18)
                name = record[18:].strip() if len(record) > 18 else f"TP{len(turnpoints)+1}"

                # Only include US turnpoints
                if self.is_in_us(lat, lon):
                    turnpoints.append({
                        'lat': lat,
                        'lon': lon,
                        'name': name
                    })
            except (ValueError, IndexError):
                continue

        if len(turnpoints) >= 2:  # Need at least 2 turnpoints for a valid task
            return {'turnpoints': turnpoints}

        return None

    def parse_igc_file(self, igc_file: Path) -> Optional[FlightTrack]:
        """
        Parse an IGC file and extract GPS coordinates and flight date

        IGC B record format:
        B HHMMSS DDMMmmmN/S DDDMMmmmE/W A PPPPP GGGGG
        Example: B1122334510234N00123456WA0123401234

        IGC H record for date:
        HFDTE<DDMMYY> or HFDTEDATE:<DDMMYY>

        Args:
            igc_file: Path to IGC file

        Returns:
            FlightTrack object or None if parsing failed
        """
        try:
            coordinates = []
            total_fixes = 0
            filtered_fixes = 0
            flight_date = None
            aircraft = None
            first_time = None
            last_time = None
            c_records = []  # Task declaration records

            with open(igc_file, 'r', encoding='latin-1', errors='ignore') as f:
                first_line = f.readline().strip()

                # Check if this is a valid IGC file (should start with A, H, or B record)
                if first_line.startswith('<!DOCTYPE') or first_line.startswith('<html'):
                    logger.debug(f"Skipping HTML file: {igc_file.name}")
                    return None

                # Check for IGC header records
                if not (first_line.startswith('A') or first_line.startswith('H')):
                    logger.debug(f"Invalid IGC file format: {igc_file.name}")
                    return None

                # Reset to beginning and parse all records
                f.seek(0)
                for line in f:
                    line = line.strip()

                    # H records contain header information including date
                    if line.startswith('HFDTE') or line.startswith('HFDT'):
                        # Extract date from HFDTE record
                        # Format: HFDTE<DDMMYY> or HFDTEDATE:<DDMMYY>
                        try:
                            # Remove 'HFDTE' or 'HFDTEDATE:' prefix
                            date_str = line.replace('HFDTE', '').replace('DATE:', '').strip()
                            if len(date_str) >= 6:
                                # Parse DDMMYY format
                                day = date_str[0:2]
                                month = date_str[2:4]
                                year = date_str[4:6]
                                # Convert 2-digit year to 4-digit (assume 20xx for dates < 50, 19xx otherwise)
                                year_full = f"20{year}" if int(year) < 50 else f"19{year}"
                                flight_date = f"{year_full}-{month}-{day}"
                        except (ValueError, IndexError):
                            pass  # Keep flight_date as None if parsing fails

                    # Extract aircraft type from various H records
                    if not aircraft and line.startswith('HF'):
                        if 'GTYGLIDERTYPE:' in line or 'GTY GLIDER TYPE:' in line:
                            aircraft = line.split(':', 1)[1].strip() if ':' in line else None
                        elif 'GIDGLIDERID:' in line or 'GID GLIDER ID:' in line:
                            aircraft = line.split(':', 1)[1].strip() if ':' in line else None

                    # C records contain task declarations
                    if line.startswith('C'):
                        c_records.append(line)

                    # B records contain GPS position data
                    if line.startswith('B') and len(line) >= 35:
                        try:
                            # Extract time from B record (positions 1-6: HHMMSS)
                            time_str = line[1:7]
                            if first_time is None:
                                first_time = time_str
                            last_time = time_str

                            # Extract latitude: positions 7-14 (DDMMmmmN/S)
                            lat_deg = int(line[7:9])
                            lat_min = float(line[9:14]) / 1000.0
                            lat_dir = line[14]
                            lat = lat_deg + lat_min / 60.0
                            if lat_dir == 'S':
                                lat = -lat

                            # Extract longitude: positions 15-23 (DDDMMmmmE/W)
                            lon_deg = int(line[15:18])
                            lon_min = float(line[18:23]) / 1000.0
                            lon_dir = line[23]
                            lon = lon_deg + lon_min / 60.0
                            if lon_dir == 'W':
                                lon = -lon

                            total_fixes += 1

                            # Only include coordinates within US boundaries
                            if self.is_in_us(lat, lon):
                                coordinates.append((lat, lon))
                            else:
                                filtered_fixes += 1
                        except (ValueError, IndexError) as e:
                            # Skip malformed B records
                            logger.debug(f"Skipping malformed B record in {igc_file.name}: {e}")
                            continue

            # Calculate duration if we have time data
            duration = None
            if first_time and last_time:
                try:
                    # Parse times as HHMMSS
                    start_h = int(first_time[0:2])
                    start_m = int(first_time[2:4])
                    start_s = int(first_time[4:6])
                    end_h = int(last_time[0:2])
                    end_m = int(last_time[2:4])
                    end_s = int(last_time[4:6])

                    # Calculate duration in minutes
                    start_minutes = start_h * 60 + start_m + start_s / 60.0
                    end_minutes = end_h * 60 + end_m + end_s / 60.0
                    duration_minutes = end_minutes - start_minutes

                    # Handle flights that cross midnight
                    if duration_minutes < 0:
                        duration_minutes += 24 * 60

                    # Format as "Xh Ym"
                    hours = int(duration_minutes // 60)
                    minutes = int(duration_minutes % 60)
                    duration = f"{hours}h {minutes}m"
                except (ValueError, IndexError):
                    pass

            # Calculate distance and speed
            distance_km = None
            avg_speed_kmh = None
            max_speed_kmh = None

            if coordinates and len(coordinates) > 1:
                # Calculate total distance
                total_distance = 0.0
                max_speed = 0.0

                for i in range(1, len(coordinates)):
                    lat1, lon1 = coordinates[i-1]
                    lat2, lon2 = coordinates[i]
                    segment_distance = self._haversine_distance(lat1, lon1, lat2, lon2)
                    total_distance += segment_distance

                    # Calculate speed for this segment (assuming 1 second between fixes)
                    # IGC files typically record every 1-5 seconds
                    # For rough speed calculation, assume average 3 seconds between fixes
                    segment_speed = (segment_distance / 3) * 3600  # km/h
                    if segment_speed > max_speed:
                        max_speed = segment_speed

                distance_km = total_distance

                # Calculate average speed from duration
                if first_time and last_time and duration:
                    try:
                        # Parse times as HHMMSS
                        start_h = int(first_time[0:2])
                        start_m = int(first_time[2:4])
                        start_s = int(first_time[4:6])
                        end_h = int(last_time[0:2])
                        end_m = int(last_time[2:4])
                        end_s = int(last_time[4:6])

                        # Calculate duration in hours
                        start_hours = start_h + start_m / 60.0 + start_s / 3600.0
                        end_hours = end_h + end_m / 60.0 + end_s / 3600.0
                        duration_hours = end_hours - start_hours

                        # Handle flights that cross midnight
                        if duration_hours < 0:
                            duration_hours += 24

                        if duration_hours > 0:
                            avg_speed_kmh = total_distance / duration_hours
                            max_speed_kmh = max_speed
                    except (ValueError, IndexError, ZeroDivisionError):
                        pass

            if coordinates:
                if filtered_fixes > 0:
                    logger.debug(
                        f"Parsed {len(coordinates)} US points from {igc_file.name} "
                        f"({filtered_fixes}/{total_fixes} fixes filtered out - outside US boundaries)"
                    )
                else:
                    logger.debug(f"Parsed {len(coordinates)} points from {igc_file.name}")

                # Parse task declaration if present
                task = self._parse_task_from_c_records(c_records) if c_records else None
                if task:
                    logger.debug(f"Found task with {len(task['turnpoints'])} turnpoints in {igc_file.name}")

                return FlightTrack(
                    filename=igc_file.name,
                    coordinates=coordinates,
                    flight_date=flight_date,
                    aircraft=aircraft,
                    duration=duration,
                    distance_km=distance_km,
                    avg_speed_kmh=avg_speed_kmh,
                    max_speed_kmh=max_speed_kmh,
                    task=task,
                )
            else:
                if total_fixes > 0:
                    logger.warning(
                        f"No GPS coordinates found in {igc_file.name} after filtering "
                        f"({total_fixes} fixes were outside US boundaries)"
                    )
                else:
                    logger.warning(f"No GPS coordinates found in {igc_file.name}")
                return None

        except Exception as e:
            logger.error(f"Failed to parse {igc_file}: {e}")
            return None

    def generate_color(self, index: int, total: int) -> str:
        """Generate a color for a flight track based on index"""
        # Use HSL color space for well-distributed colors
        hue = (index * 360 / total) % 360
        return f'hsl({hue}, 70%, 50%)'

    def clean_pilot_name_for_display(self, pilot_name: str) -> str:
        """
        Clean up pilot name for display in UI:
        - Remove underscores
        - Remove region codes like (US_-_R1), (BE), etc.
        """
        import re
        cleaned = re.sub(r'\s*\([^)]*\)', '', pilot_name)
        cleaned = cleaned.replace('_', ' ')
        return cleaned.strip()

    def _parse_sterling_waypoints_kmz(self, kmz_file: Path):
        """Parse Sterling waypoints from KMZ file"""
        import xml.etree.ElementTree as ET
        import zipfile
        import tempfile
        import shutil

        waypoints = []

        try:
            # Extract KMZ (it's a ZIP file)
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(kmz_file, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)

                # Find the KML file
                kml_files = list(Path(temp_dir).rglob('*.kml'))
                if not kml_files:
                    logger.error("No KML file found in KMZ")
                    return waypoints

                kml_file = kml_files[0]

                # Parse KML
                tree = ET.parse(kml_file)
                root = tree.getroot()

                # KML namespace
                ns = {'kml': 'http://earth.google.com/kml/2.0'}

                # Get all placemarks
                placemarks = root.findall('.//kml:Placemark', ns)

                for placemark in placemarks:
                    # Get name
                    name_elem = placemark.find('.//kml:name', ns)
                    name = name_elem.text.strip() if name_elem is not None else 'Unknown'

                    # Get description
                    desc_elem = placemark.find('.//kml:description', ns)
                    description = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ''

                    # Get coordinates
                    coord_elem = placemark.find('.//kml:Point/kml:coordinates', ns)
                    if coord_elem is None:
                        continue

                    coords = coord_elem.text.strip().split(',')
                    if len(coords) < 2:
                        continue

                    try:
                        lon = float(coords[0])
                        lat = float(coords[1])
                    except (ValueError, IndexError):
                        continue

                    # Get icon type
                    icon_elem = placemark.find('.//kml:Icon/kml:href', ns)
                    waypoint_type = 'other'  # default

                    if icon_elem is not None:
                        icon_href = icon_elem.text
                        if 'palette-3.png' in icon_href:
                            waypoint_type = 'home'  # Sterling (home field)
                        elif 'palette-2.png' in icon_href:
                            waypoint_type = 'airport'  # Other airports
                        elif 'palette-5.png' in icon_href:
                            waypoint_type = 'landmark'  # Turnpoints/landmarks
                        elif 'palette-4.png' in icon_href:
                            waypoint_type = 'default'

                    waypoints.append({
                        'name': name,
                        'lat': lat,
                        'lon': lon,
                        'type': waypoint_type,
                        'description': description
                    })

                logger.info(f"Parsed {len(waypoints)} waypoints from KMZ")

        except FileNotFoundError:
            logger.warning(f"Waypoint file not found: {kmz_file}")
        except Exception as e:
            logger.error(f"Error parsing KMZ file: {e}")

        return waypoints

    def _add_custom_layer_selector(self, flight_map):
        """Add custom layer selector UI (Google Maps style)"""

        layer_selector_html = '''
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

            /* Improve VFR chart rendering quality */
            .vfr-tiles {
                image-rendering: -webkit-optimize-contrast;
                image-rendering: crisp-edges;
                -ms-interpolation-mode: nearest-neighbor;
            }

            /* Override Leaflet control positions and z-index */
            .leaflet-control {
                z-index: 800 !important;
            }

            /* Move zoom controls to bottom-right */
            .leaflet-top.leaflet-left {
                top: auto !important;
                bottom: 16px !important;
                left: auto !important;
                right: 16px !important;
            }

            /* Modern styling for zoom controls */
            .leaflet-control-zoom {
                border: none !important;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
                border-radius: 12px !important;
                overflow: hidden;
            }

            .leaflet-control-zoom a {
                width: 40px !important;
                height: 40px !important;
                line-height: 40px !important;
                font-size: 20px !important;
                border: none !important;
                background: rgba(255, 255, 255, 0.98) !important;
                backdrop-filter: blur(10px) !important;
                color: #2d3748 !important;
                transition: all 0.2s ease !important;
            }

            .leaflet-control-zoom a:hover {
                background: linear-gradient(135deg, #003087 0%, #0052CC 100%) !important;
                color: white !important;
                transform: scale(1.05);
            }

            /* Modern styling for fullscreen control */
            .leaflet-control-fullscreen {
                border: none !important;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important;
                border-radius: 12px !important;
                margin-bottom: 8px !important;
            }

            .leaflet-control-fullscreen a {
                width: 40px !important;
                height: 40px !important;
                background: rgba(255, 255, 255, 0.98) !important;
                backdrop-filter: blur(10px) !important;
                border-radius: 12px !important;
                transition: all 0.2s ease !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }

            .leaflet-control-fullscreen a:hover {
                background: linear-gradient(135deg, #003087 0%, #0052CC 100%) !important;
                transform: scale(1.05);
            }

            .leaflet-control-fullscreen a:hover svg path {
                stroke: white !important;
            }

            .layer-selector {
                position: fixed;
                bottom: 16px;
                left: 16px;
                z-index: 10000;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            }

            .layer-selector-button {
                background: rgba(255, 255, 255, 0.98);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 12px;
                padding: 0;
                cursor: pointer;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                width: 48px;
                height: 48px;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s ease;
            }

            .layer-selector-button:hover {
                background: linear-gradient(135deg, #003087 0%, #0052CC 100%);
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
            }

            .layer-selector-button:hover svg path {
                fill: white;
                stroke: white;
            }

            .layer-selector-button:active {
                transform: translateY(0);
            }

            .layer-selector-panel {
                display: none;
                position: absolute;
                bottom: 56px;
                left: 0;
                background: rgba(255, 255, 255, 0.98);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 16px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
                min-width: 260px;
                overflow: hidden;
                z-index: 10001;
                animation: slideUp 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            }

            @keyframes slideUp {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            .layer-selector-panel.open {
                display: block;
            }

            .layer-selector-header {
                padding: 16px 20px;
                font-weight: 600;
                font-size: 14px;
                letter-spacing: 0.5px;
                text-transform: uppercase;
                color: #4a5568;
                background: linear-gradient(135deg, #f6f8fb 0%, #e9ecef 100%);
            }

            .layer-option {
                padding: 12px 20px;
                cursor: pointer;
                display: flex;
                align-items: center;
                font-size: 14px;
                transition: all 0.2s ease;
                border-bottom: 1px solid rgba(0, 0, 0, 0.04);
                position: relative;
            }

            .layer-option::before {
                content: '';
                position: absolute;
                left: 0;
                top: 0;
                bottom: 0;
                width: 3px;
                background: linear-gradient(135deg, #003087 0%, #0052CC 100%);
                transform: scaleY(0);
                transition: transform 0.2s ease;
            }

            .layer-option:hover {
                background: linear-gradient(90deg, rgba(102, 126, 234, 0.08) 0%, transparent 100%);
            }

            .layer-option.active {
                background: linear-gradient(90deg, rgba(102, 126, 234, 0.12) 0%, rgba(102, 126, 234, 0.04) 100%);
                font-weight: 500;
            }

            .layer-option.active::before {
                transform: scaleY(1);
            }

            .layer-option-icon {
                width: 24px;
                height: 24px;
                margin-right: 12px;
                font-size: 18px;
                display: flex;
                align-items: center;
                justify-content: center;
            }

            .layer-option-text {
                flex: 1;
                color: #2d3748;
            }

            .layer-option-check {
                color: #003087;
                font-weight: bold;
                margin-left: 8px;
                font-size: 16px;
            }

            /* Loading overlay */
            .loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: linear-gradient(135deg, #003087 0%, #0052CC 100%);
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                z-index: 99999;
                transition: opacity 0.5s ease, visibility 0.5s ease;
            }

            .loading-overlay.hidden {
                opacity: 0;
                visibility: hidden;
            }

            .loading-spinner {
                width: 60px;
                height: 60px;
                border: 4px solid rgba(255, 255, 255, 0.3);
                border-top-color: white;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }

            @keyframes spin {
                to { transform: rotate(360deg); }
            }

            .loading-text {
                margin-top: 24px;
                color: white;
                font-size: 18px;
                font-weight: 500;
                text-align: center;
            }

            .loading-subtext {
                margin-top: 8px;
                color: rgba(255, 255, 255, 0.8);
                font-size: 14px;
            }

            .loading-progress {
                margin-top: 24px;
                width: 300px;
                text-align: center;
            }

            .progress-counter {
                color: white;
                font-size: 16px;
                font-weight: 500;
                margin-bottom: 12px;
                font-variant-numeric: tabular-nums;
            }

            .progress-bar-container {
                width: 100%;
                height: 6px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 3px;
                overflow: hidden;
            }

            .progress-bar {
                height: 100%;
                background: linear-gradient(90deg, #00d4ff 0%, #00ff88 100%);
                width: 0%;
                transition: width 0.3s ease;
                border-radius: 3px;
            }
        </style>

        <div class="layer-selector">
            <button class="layer-selector-button" onclick="toggleLayerSelector(event)" title="Change map layer">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="transition: all 0.2s ease;">
                    <path d="M12 3L4 7L12 11L20 7L12 3Z" fill="#2D3748" stroke="#2D3748" stroke-width="1.5" stroke-linejoin="round"/>
                    <path d="M4 12L12 16L20 12" stroke="#2D3748" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    <path d="M4 17L12 21L20 17" stroke="#2D3748" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </button>

            <div class="layer-selector-panel" id="layerSelectorPanel">
                <div class="layer-selector-header">Map Type</div>

                <div class="layer-option active" data-layer="esri-topo" onclick="switchLayer('esri-topo', event)">
                    <div class="layer-option-icon">🏔️</div>
                    <div class="layer-option-text">Terrain</div>
                    <div class="layer-option-check">✓</div>
                </div>

                <div class="layer-option" data-layer="satellite" onclick="switchLayer('satellite', event)">
                    <div class="layer-option-icon">🛰️</div>
                    <div class="layer-option-text">Satellite</div>
                    <div class="layer-option-check"></div>
                </div>

                <div class="layer-option" data-layer="usgs" onclick="switchLayer('usgs', event)">
                    <div class="layer-option-icon">🇺🇸</div>
                    <div class="layer-option-text">USGS Topo</div>
                    <div class="layer-option-check"></div>
                </div>

                <div class="layer-option" data-layer="light" onclick="switchLayer('light', event)">
                    <div class="layer-option-icon">☀️</div>
                    <div class="layer-option-text">Light</div>
                    <div class="layer-option-check"></div>
                </div>

                <div class="layer-option" data-layer="vfr-local" onclick="switchLayer('vfr-local', event)">
                    <div class="layer-option-icon">✈️</div>
                    <div class="layer-option-text">VFR Sectional</div>
                    <div class="layer-option-check"></div>
                </div>
                <div class="layer-option" data-layer="satellite-dated" onclick="switchLayer('satellite-dated', event)">
                    <div class="layer-option-icon">🛰️</div>
                    <div class="layer-option-text">Satellite (Flight Date)</div>
                    <div class="layer-option-check"></div>
                </div>
            </div>
        </div>

        <script>
            var currentLayer = 'vfr-local';
            var layerUrls = {
                'esri-topo': {
                    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
                    attr: 'Tiles &copy; Esri',
                    options: {
                        maxZoom: 18,
                        detectRetina: true
                    }
                },
                'satellite': {
                    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                    attr: 'Tiles &copy; Esri',
                    options: {
                        maxZoom: 18,
                        detectRetina: true
                    }
                },
                'usgs': {
                    url: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}',
                    attr: 'Tiles courtesy of the U.S. Geological Survey',
                    options: {
                        maxZoom: 18,
                        detectRetina: true
                    }
                },
                'light': {
                    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
                    attr: '&copy; OpenStreetMap contributors &copy; CARTO',
                    options: {
                        maxZoom: 18,
                        detectRetina: true
                    }
                },
                'vfr-local': {
                    url: '{VFR_TILE_URL}',
                    attr: 'VFR Charts &copy; FAA (Local High-Resolution 300 DPI)',
                    options: {
                        minZoom: 8,
                        maxZoom: 13,
                        maxNativeZoom: 12,
                        updateWhenZooming: false,
                        keepBuffer: 4,
                        className: 'vfr-tiles'
                    }
                },
                'satellite-dated': {
                    url: '{SATELLITE_TILE_URL}',
                    attr: 'NASA EOSDIS GIBS VIIRS',
                    options: {
                        minZoom: 8,
                        maxZoom: 13,
                        maxNativeZoom: 9,
                        updateWhenZooming: false,
                        keepBuffer: 4,
                        errorTileUrl: 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
                    }
                }
            };

            var tileLayer = null;
            var terrainBaseLayer = null;  // Terrain fallback for satellite mode
            var mapInstance = null;

            // Track initialization progress
            var initComponents = {
                layerSelector: false,
                heatmapToggle: false,
                routesToggle: false,
                waypointToggle: false,
                tasksToggle: false,
                filterPanel: false
            };

            // Track flight loading progress
            var flightLoadProgress = {
                totalFlights: 0,
                loadedFlights: 0,
                startTime: Date.now()
            };

            function updateLoadingProgress(loaded, total) {
                var loadedCountEl = document.getElementById('loadedCount');
                var totalCountEl = document.getElementById('totalCount');
                var progressBar = document.getElementById('progressBar');

                if (loadedCountEl) loadedCountEl.textContent = loaded;
                if (totalCountEl) totalCountEl.textContent = total;

                if (progressBar && total > 0) {
                    var percentage = (loaded / total) * 100;
                    progressBar.style.width = percentage + '%';
                }
            }

            function checkAllInitialized() {
                var allReady = Object.values(initComponents).every(function(v) { return v; });
                if (allReady) {
                    console.log('All components initialized - hiding loading overlay');
                    var overlay = document.getElementById('loadingOverlay');
                    if (overlay) {
                        overlay.classList.add('hidden');
                    }
                } else {
                    console.log('Components status:', initComponents);
                }
            }

            // Wait for map to be fully loaded
            function waitForMap(callback, attempt) {
                attempt = attempt || 0;
                console.log('Waiting for map... attempt', attempt + 1);

                var maps = document.querySelectorAll('.folium-map');
                if (maps.length === 0) {
                    if (attempt < 20) {
                        setTimeout(function() { waitForMap(callback, attempt + 1); }, 500);
                    }
                    return;
                }

                var mapDiv = maps[0];
                var mapId = mapDiv.id;

                // Search for the map object in window properties
                var foundMap = null;
                for (var key in window) {
                    try {
                        if (window[key] && typeof window[key] === 'object' && typeof window[key].eachLayer === 'function') {
                            foundMap = window[key];
                            console.log('Found map object at window.' + key);
                            break;
                        }
                    } catch(e) {
                        // Skip
                    }
                }

                if (foundMap) {
                    console.log('Map is ready!');
                    callback(foundMap);
                } else if (attempt < 20) {
                    // Keep trying for up to 10 seconds
                    setTimeout(function() { waitForMap(callback, attempt + 1); }, 500);
                } else {
                    console.error('Map not found after 10 seconds');
                }
            }

            // Initialize when map is ready
            waitForMap(function(map) {
                mapInstance = map;
                console.log('Layer selector initialized with map');

                // Set up progress tracking for flight layers
                var totalFlightTracks = 0;
                for (var i = 0; i < trackMetadata.length; i++) {
                    if (trackMetadata[i]['type'] == 'line') {
                        totalFlightTracks++;
                    }
                }

                console.log('Total flight tracks to load:', totalFlightTracks);

                // Count flight track layers on the map
                var flightTrackLayers = [];
                mapInstance.eachLayer(function(layer) {
                    // Check if this is a PolyLine (flight track)
                    if (layer instanceof L.Polyline && !(layer instanceof L.Polygon)) {
                        // Exclude heatmap polylines by checking if it has our custom options
                        if (layer.options && typeof layer.options.flightIdx === 'number') {
                            flightTrackLayers.push(layer);
                        }
                    }
                });

                console.log('Found', flightTrackLayers.length, 'flight track layers');

                // Animate progress counter
                var currentProgress = 0;
                var targetProgress = flightTrackLayers.length;
                var progressInterval = setInterval(function() {
                    if (currentProgress < targetProgress) {
                        // Increment by chunks for smooth animation
                        var increment = Math.max(1, Math.ceil((targetProgress - currentProgress) / 10));
                        currentProgress = Math.min(currentProgress + increment, targetProgress);
                        updateLoadingProgress(currentProgress, totalFlightTracks);

                        if (currentProgress % 10 === 0 || currentProgress === targetProgress) {
                            console.log('Loading progress:', currentProgress, '/', totalFlightTracks);
                        }
                    } else {
                        clearInterval(progressInterval);
                        console.log('All flight tracks loaded!');
                    }
                }, 50); // Update every 50ms for smooth animation

                // Get the base tile layer
                var layerCount = 0;
                mapInstance.eachLayer(function(layer) {
                    layerCount++;

                    // Tile layer has _url
                    if (layer._url && !tileLayer) {
                        tileLayer = layer;
                        console.log('Found tile layer');
                    }
                });

                console.log('Total layers:', layerCount);
                console.log('Tile layer found:', !!tileLayer);

                if (!tileLayer) {
                    console.error('Could not find tile layer!');
                } else {
                    // Enhance initial tile layer with better rendering options
                    var initialLayerOptions = layerUrls[currentLayer].options || {};
                    if (initialLayerOptions.detectRetina && L.Browser.retina) {
                        tileLayer.options.detectRetina = true;
                    }
                    console.log('Enhanced initial tile layer with rendering options');
                }

                // Add fullscreen icon - try multiple selectors
                console.log('Looking for fullscreen button...');

                var fullscreenBtn = document.querySelector('.leaflet-control-fullscreen a');
                console.log('Fullscreen button (.leaflet-control-fullscreen a):', fullscreenBtn);

                if (!fullscreenBtn) {
                    fullscreenBtn = document.querySelector('.leaflet-control-fullscreen');
                    console.log('Fullscreen button (.leaflet-control-fullscreen):', fullscreenBtn);
                }

                if (!fullscreenBtn) {
                    var allControls = document.querySelectorAll('.leaflet-control');
                    console.log('All leaflet controls found:', allControls.length);
                    allControls.forEach(function(ctrl, i) {
                        console.log('Control', i, ':', ctrl.className);
                    });
                }

                if (fullscreenBtn) {
                    fullscreenBtn.innerHTML = `
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="transition: all 0.2s ease;">
                            <path d="M8 3H5C3.89543 3 3 3.89543 3 5V8" stroke="#2D3748" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M21 8V5C21 3.89543 20.1046 3 19 3H16" stroke="#2D3748" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M16 21H19C20.1046 21 21 20.1046 21 19V16" stroke="#2D3748" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M3 16V19C3 20.1046 3.89543 21 5 21H8" stroke="#2D3748" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    `;
                    console.log('Fullscreen icon added to:', fullscreenBtn);
                } else {
                    console.error('Fullscreen button not found!');
                }

                // Mark layer selector as initialized
                initComponents.layerSelector = true;
                checkAllInitialized();
            });

            function toggleLayerSelector(e) {
                if (e) e.stopPropagation();
                var panel = document.getElementById('layerSelectorPanel');
                panel.classList.toggle('open');
                console.log('Layer selector toggled, open:', panel.classList.contains('open'));
            }

            function switchLayer(layerName, e) {
                if (e) e.stopPropagation();

                console.log('Switching to layer:', layerName);

                if (!mapInstance) {
                    console.error('Map instance not found');
                    return;
                }

                if (!tileLayer) {
                    console.error('Tile layer not found');
                    return;
                }

                currentLayer = layerName;

                // Update tile layer URL and attribution
                var newLayer = layerUrls[layerName];
                console.log('New layer URL:', newLayer.url);

                // Remove old layers
                mapInstance.removeLayer(tileLayer);
                if (terrainBaseLayer) {
                    mapInstance.removeLayer(terrainBaseLayer);
                    terrainBaseLayer = null;
                }

                // Note: No terrain base layer for satellite mode - MODIS fallback provides full coverage

                // Create new tile layer with layer-specific options
                var tileOptions = Object.assign({}, newLayer.options || {}, {
                    attribution: newLayer.attr + (layerName === 'satellite-dated' && currentSatelliteDate ? ' (' + currentSatelliteDate + ')' : '')
                });
                tileLayer = L.tileLayer(newLayer.url, tileOptions);

                // Add it to map
                tileLayer.addTo(mapInstance);

                // Send tile layer to back so overlays (flight tracks, etc) are on top
                tileLayer.bringToBack();

                // Update active state in UI
                document.querySelectorAll('.layer-option').forEach(function(option) {
                    var check = option.querySelector('.layer-option-check');
                    if (option.dataset.layer === layerName) {
                        option.classList.add('active');
                        check.textContent = '✓';
                    } else {
                        option.classList.remove('active');
                        check.textContent = '';
                    }
                });

                // Show/hide satellite date picker (keep filter active across all layers)
                if (satelliteDateIndicator) {
                    var dateButton = document.getElementById('satellite-date-button');
                    var hasActiveFilter = dateButton && dateButton.textContent !== 'Select date...';

                    if (layerName === 'satellite-dated') {
                        // Show the date picker when on satellite layer (can pick dates)
                        satelliteDateIndicator.style.display = 'flex';

                        // Reapply date filter if one is active
                        if (hasActiveFilter && typeof filterByDate === 'function') {
                            filterByDate(dateButton.textContent);
                        }
                    } else if (hasActiveFilter) {
                        // On other layers, still show the date indicator (but can't change date)
                        // This lets users know flights are filtered by date
                        satelliteDateIndicator.style.display = 'flex';
                        // Note: Date filter remains active, flights stay filtered
                    } else {
                        // No active filter and not on satellite layer - hide completely
                        satelliteDateIndicator.style.display = 'none';
                    }
                }

                console.log('Layer switched successfully');

                // Close panel
                document.getElementById('layerSelectorPanel').classList.remove('open');
            }

            // Satellite date switching functionality
            var currentSatelliteDate = null;
            var satelliteDateIndicator = null;

            function updateSatelliteDate(date) {
                if (!date || date === 'unknown') {
                    console.log('Invalid date for satellite imagery:', date);
                    return;
                }

                currentSatelliteDate = date;
                console.log('Updating satellite imagery to date:', date);

                // Update the satellite layer URL if it's currently active
                if (currentLayer === 'satellite-dated' && tileLayer && mapInstance) {
                    var satelliteLayerConfig = layerUrls['satellite-dated'];
                    var baseUrl = satelliteLayerConfig.url;

                    // Replace the date placeholder in URL (works for both local and github-pages modes)
                    var newUrl = baseUrl.replace(/\\/\\d{4}-\\d{2}-\\d{2}\\//, '/' + date + '/');

                    console.log('New satellite URL:', newUrl);

                    // Remove old tile layer
                    mapInstance.removeLayer(tileLayer);

                    // Create new tile layer with updated date
                    var tileOptions = Object.assign({}, satelliteLayerConfig.options || {}, {
                        attribution: satelliteLayerConfig.attr + ' (' + date + ')'
                    });
                    tileLayer = L.tileLayer(newUrl, tileOptions);
                    tileLayer.addTo(mapInstance);

                    // Send to back so overlays (flight tracks, etc) are on top
                    tileLayer.bringToBack();
                }

                // Update date indicator and date button
                if (satelliteDateIndicator) {
                    var dateButton = document.getElementById('satellite-date-button');
                    if (dateButton) {
                        dateButton.textContent = date;
                    }
                    satelliteDateIndicator.style.display = 'flex';
                }

                // IMPORTANT: Also filter flights to show only this date
                // This ensures satellite imagery and flights are synchronized
                if (typeof filterByDate === 'function') {
                    filterByDate(date);
                } else {
                    console.warn('filterByDate function not available yet - flights will not be filtered');
                }
            }

            function setupSatelliteDateSwitching() {
                // Store current selected date
                var selectedDate = null;
                if (typeof availableSatelliteDates !== 'undefined' && availableSatelliteDates.length > 0) {
                    selectedDate = availableSatelliteDates[availableSatelliteDates.length - 1];
                }

                // Create date picker UI container
                satelliteDateIndicator = document.createElement('div');
                satelliteDateIndicator.style.cssText = `
                    position: absolute;
                    bottom: 30px;
                    left: 50%;
                    transform: translateX(-50%);
                    z-index: 1000;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                `;

                // Create main date display button
                var dateDisplayContainer = document.createElement('div');
                dateDisplayContainer.style.cssText = `
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    padding: 10px 15px;
                    border-radius: 20px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.15);
                    font-size: 13px;
                    color: #333;
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    border: 1px solid rgba(102, 126, 234, 0.2);
                    position: relative;
                `;

                var label = document.createElement('strong');
                label.textContent = 'Flight Date:';
                label.style.color = '#666';

                var dateButton = document.createElement('button');
                dateButton.id = 'satellite-date-button';
                dateButton.textContent = selectedDate || 'Select date...';
                dateButton.style.cssText = `
                    padding: 5px 10px;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    background: white;
                    color: #333;
                    font-size: 13px;
                    cursor: pointer;
                    outline: none;
                    transition: border-color 0.2s;
                    min-width: 110px;
                `;
                dateButton.onmouseover = function() { this.style.borderColor = '#667eea'; };
                dateButton.onmouseout = function() { this.style.borderColor = '#ddd'; };

                // Create calendar popup
                var calendarPopup = document.createElement('div');
                calendarPopup.id = 'calendar-popup';
                calendarPopup.style.cssText = `
                    position: absolute;
                    bottom: 50px;
                    left: 50%;
                    transform: translateX(-50%);
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
                    padding: 15px;
                    display: none;
                    min-width: 280px;
                    z-index: 10001;
                `;

                // Build calendar UI
                function buildCalendar(year, month) {
                    calendarPopup.innerHTML = '';

                    // Header with month/year navigation
                    var header = document.createElement('div');
                    header.style.cssText = `
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 10px;
                        padding-bottom: 10px;
                        border-bottom: 1px solid #eee;
                    `;

                    // Previous month button
                    var prevButton = document.createElement('button');
                    prevButton.innerHTML = '◀';
                    prevButton.style.cssText = `
                        background: none;
                        border: none;
                        cursor: pointer;
                        font-size: 14px;
                        padding: 5px 10px;
                        color: #667eea;
                        flex-shrink: 0;
                    `;
                    prevButton.onclick = function(e) {
                        e.stopPropagation(); // Prevent calendar from closing
                        var newMonth = month - 1;
                        var newYear = year;
                        if (newMonth < 0) {
                            newMonth = 11;
                            newYear--;
                        }
                        buildCalendar(newYear, newMonth);
                    };

                    // Month/Year selector container
                    var selectorContainer = document.createElement('div');
                    selectorContainer.style.cssText = `
                        display: flex;
                        gap: 8px;
                        align-items: center;
                    `;

                    // Month dropdown
                    var monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                                    'July', 'August', 'September', 'October', 'November', 'December'];
                    var monthSelect = document.createElement('select');
                    monthSelect.style.cssText = `
                        padding: 4px 8px;
                        border: 1px solid #ddd;
                        border-radius: 6px;
                        background: white;
                        color: #333;
                        font-size: 13px;
                        cursor: pointer;
                        outline: none;
                    `;
                    monthNames.forEach(function(name, idx) {
                        var option = document.createElement('option');
                        option.value = idx;
                        option.textContent = name;
                        if (idx === month) {
                            option.selected = true;
                        }
                        monthSelect.appendChild(option);
                    });
                    monthSelect.onchange = function() {
                        buildCalendar(year, parseInt(this.value));
                    };

                    // Year dropdown - get range from available dates
                    var yearSelect = document.createElement('select');
                    yearSelect.style.cssText = monthSelect.style.cssText;

                    var years = new Set();
                    if (typeof availableSatelliteDates !== 'undefined') {
                        availableSatelliteDates.forEach(function(date) {
                            var y = parseInt(date.split('-')[0]);
                            years.add(y);
                        });
                    }
                    var sortedYears = Array.from(years).sort();

                    sortedYears.forEach(function(y) {
                        var option = document.createElement('option');
                        option.value = y;
                        option.textContent = y;
                        if (y === year) {
                            option.selected = true;
                        }
                        yearSelect.appendChild(option);
                    });
                    yearSelect.onchange = function() {
                        buildCalendar(parseInt(this.value), month);
                    };

                    selectorContainer.appendChild(monthSelect);
                    selectorContainer.appendChild(yearSelect);

                    // Next month button
                    var nextButton = document.createElement('button');
                    nextButton.innerHTML = '▶';
                    nextButton.style.cssText = prevButton.style.cssText;
                    nextButton.onclick = function(e) {
                        e.stopPropagation(); // Prevent calendar from closing
                        var newMonth = month + 1;
                        var newYear = year;
                        if (newMonth > 11) {
                            newMonth = 0;
                            newYear++;
                        }
                        buildCalendar(newYear, newMonth);
                    };

                    // Close button for calendar popup
                    var closeButton = document.createElement('button');
                    closeButton.innerHTML = '✕';
                    closeButton.title = 'Close calendar';
                    closeButton.style.cssText = `
                        background: none;
                        border: none;
                        cursor: pointer;
                        font-size: 18px;
                        padding: 0px 5px;
                        color: #999;
                        flex-shrink: 0;
                        margin-left: 10px;
                    `;
                    closeButton.onmouseover = function() { this.style.color = '#667eea'; };
                    closeButton.onmouseout = function() { this.style.color = '#999'; };
                    closeButton.onclick = function() {
                        calendarPopup.style.display = 'none';
                    };

                    header.appendChild(prevButton);
                    header.appendChild(selectorContainer);
                    header.appendChild(nextButton);
                    header.appendChild(closeButton);
                    calendarPopup.appendChild(header);

                    // Day headers
                    var dayHeaders = document.createElement('div');
                    dayHeaders.style.cssText = `
                        display: grid;
                        grid-template-columns: repeat(7, 1fr);
                        gap: 5px;
                        margin-bottom: 5px;
                    `;
                    ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].forEach(function(day) {
                        var dayHeader = document.createElement('div');
                        dayHeader.textContent = day;
                        dayHeader.style.cssText = `
                            text-align: center;
                            font-size: 11px;
                            font-weight: bold;
                            color: #999;
                            padding: 5px 0;
                        `;
                        dayHeaders.appendChild(dayHeader);
                    });
                    calendarPopup.appendChild(dayHeaders);

                    // Calendar grid
                    var grid = document.createElement('div');
                    grid.style.cssText = `
                        display: grid;
                        grid-template-columns: repeat(7, 1fr);
                        gap: 5px;
                    `;

                    // Get first day of month and number of days
                    var firstDay = new Date(year, month, 1).getDay();
                    var daysInMonth = new Date(year, month + 1, 0).getDate();

                    // Convert available dates to Set for quick lookup
                    var availableDatesSet = new Set(availableSatelliteDates || []);

                    // Add empty cells for days before month starts
                    for (var i = 0; i < firstDay; i++) {
                        var emptyCell = document.createElement('div');
                        emptyCell.style.padding = '8px';
                        grid.appendChild(emptyCell);
                    }

                    // Add day cells
                    for (var day = 1; day <= daysInMonth; day++) {
                        var dateStr = year + '-' +
                                    String(month + 1).padStart(2, '0') + '-' +
                                    String(day).padStart(2, '0');
                        var isAvailable = availableDatesSet.has(dateStr);

                        var dayCell = document.createElement('button');
                        dayCell.textContent = day;
                        dayCell.style.cssText = `
                            padding: 8px;
                            border: 1px solid ${isAvailable ? '#ddd' : 'transparent'};
                            border-radius: 6px;
                            background: ${isAvailable ? 'white' : 'transparent'};
                            color: ${isAvailable ? '#333' : '#ccc'};
                            cursor: ${isAvailable ? 'pointer' : 'not-allowed'};
                            font-size: 13px;
                            transition: all 0.2s;
                            ${dateStr === selectedDate ? 'background: #667eea; color: white; border-color: #667eea;' : ''}
                        `;

                        if (isAvailable) {
                            (function(date) {
                                dayCell.onclick = function() {
                                    selectedDate = date;
                                    dateButton.textContent = date;
                                    calendarPopup.style.display = 'none';

                                    console.log('Calendar date selected:', date);

                                    // Switch to satellite layer if not already on it
                                    if (currentLayer !== 'satellite-dated' && typeof switchLayer === 'function') {
                                        switchLayer('satellite-dated');
                                    }

                                    // Update satellite imagery and filter flights
                                    updateSatelliteDate(date);
                                };
                                dayCell.onmouseover = function() {
                                    if (date !== selectedDate) {
                                        this.style.background = '#f0f0f0';
                                        this.style.borderColor = '#667eea';
                                    }
                                };
                                dayCell.onmouseout = function() {
                                    if (date !== selectedDate) {
                                        this.style.background = 'white';
                                        this.style.borderColor = '#ddd';
                                    }
                                };
                            })(dateStr);
                        }

                        grid.appendChild(dayCell);
                    }

                    calendarPopup.appendChild(grid);
                }

                // Initialize calendar to most recent date's month
                if (selectedDate) {
                    var parts = selectedDate.split('-');
                    var initialYear = parseInt(parts[0]);
                    var initialMonth = parseInt(parts[1]) - 1;
                    buildCalendar(initialYear, initialMonth);
                }

                // Toggle calendar on button click
                dateButton.onclick = function() {
                    var isVisible = calendarPopup.style.display === 'block';
                    calendarPopup.style.display = isVisible ? 'none' : 'block';
                };

                // Close calendar when clicking outside
                document.addEventListener('click', function(e) {
                    if (!dateDisplayContainer.contains(e.target) && !calendarPopup.contains(e.target)) {
                        calendarPopup.style.display = 'none';
                    }
                });

                // Assemble the UI
                dateDisplayContainer.appendChild(label);
                dateDisplayContainer.appendChild(dateButton);
                dateDisplayContainer.appendChild(calendarPopup);

                satelliteDateIndicator.appendChild(dateDisplayContainer);
                document.querySelector('.folium-map').appendChild(satelliteDateIndicator);

                // Wait for map to be ready, then attach click handlers to tracks
                waitForMap(function() {
                    if (!mapInstance) {
                        console.error('Map instance not available');
                        return;
                    }

                    // Attach click handlers to all track layers
                    mapInstance.eachLayer(function(layer) {
                        if (layer.options && layer.options.flightDate) {
                            layer.on('click', function(e) {
                                var date = layer.options.flightDate;
                                console.log('Flight track clicked, date:', date);
                                updateSatelliteDate(date);

                                // If not on satellite layer, show a hint
                                if (currentLayer !== 'satellite-dated') {
                                    var hint = document.createElement('div');
                                    hint.style.cssText = `
                                        position: absolute;
                                        top: 50%;
                                        left: 50%;
                                        transform: translate(-50%, -50%);
                                        background: rgba(102, 126, 234, 0.95);
                                        color: white;
                                        padding: 15px 25px;
                                        border-radius: 10px;
                                        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                                        z-index: 10001;
                                        font-size: 14px;
                                        pointer-events: none;
                                    `;
                                    hint.textContent = 'Switch to "Satellite (Flight Date)" layer to view imagery from ' + date;
                                    document.querySelector('.folium-map').appendChild(hint);

                                    setTimeout(function() {
                                        hint.style.transition = 'opacity 0.3s';
                                        hint.style.opacity = '0';
                                        setTimeout(function() { hint.remove(); }, 300);
                                    }, 2500);
                                }
                            });
                        }
                    });

                    console.log('Satellite date switching enabled');
                });
            }

            // Initialize satellite date switching after page load
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', setupSatelliteDateSwitching);
            } else {
                setupSatelliteDateSwitching();
            }

            // Close panel when clicking outside
            document.addEventListener('click', function(event) {
                if (!event.target.closest('.layer-selector')) {
                    document.getElementById('layerSelectorPanel').classList.remove('open');
                }
            });
        </script>
        '''

        flight_map.get_root().html.add_child(folium.Element(layer_selector_html))

    def _add_custom_filters(self, flight_map, tracks_by_year, tracks_by_pilot_display, pilot_display_to_raw, track_metadata):
        """Add custom Excel-style dropdown filters to the map"""

        # Build year checkboxes
        year_checkboxes = []
        for year in sorted(tracks_by_year.keys(), reverse=True):
            count = len(tracks_by_year[year])
            year_checkboxes.append(f'''
                <label class="filter-item">
                    <input type="checkbox" class="year-filter" value="{year}" checked>
                    <span>{year} ({count} flights)</span>
                </label>
            ''')

        # Build pilot checkboxes - pilots are already grouped by display name
        pilot_checkboxes = []
        for pilot_display_name in sorted(tracks_by_pilot_display.keys()):
            count = len(tracks_by_pilot_display[pilot_display_name])
            # Use display name as value (will map back to raw names in JS)
            pilot_checkboxes.append(f'''
                <label class="filter-item">
                    <input type="checkbox" class="pilot-filter" value="{pilot_display_name}" checked>
                    <span>{pilot_display_name} ({count} flights)</span>
                </label>
            ''')

        filter_html = f'''
        <style>
            .filter-panel {{
                position: fixed;
                top: 260px;
                left: 16px;
                background: rgba(255, 255, 255, 0.98);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 16px;
                padding: 16px;
                z-index: 9998;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 14px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
                min-width: 240px;
            }}

            .filter-title {{
                font-weight: 600;
                margin-bottom: 12px;
                font-size: 16px;
                color: #2d3748;
                letter-spacing: 0.3px;
            }}

            .filter-dropdown {{
                position: relative;
                margin-bottom: 8px;
            }}

            .filter-button {{
                background: linear-gradient(135deg, #f6f8fb 0%, #e9ecef 100%);
                border: 1px solid rgba(0, 0, 0, 0.08);
                padding: 10px 35px 10px 14px;
                cursor: pointer;
                width: 100%;
                text-align: left;
                border-radius: 10px;
                position: relative;
                font-weight: 500;
                color: #2d3748;
                transition: all 0.2s ease;
            }}

            .filter-button:hover {{
                background: linear-gradient(135deg, #eef1f5 0%, #dfe3e8 100%);
                border-color: rgba(102, 126, 234, 0.3);
                transform: translateY(-1px);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            }}

            .filter-button::after {{
                content: "▼";
                position: absolute;
                right: 12px;
                top: 50%;
                transform: translateY(-50%);
                font-size: 10px;
                color: #003087;
                transition: transform 0.2s ease;
            }}

            .filter-dropdown.open .filter-button::after {{
                transform: translateY(-50%) rotate(180deg);
            }}

            .filter-dropdown-content {{
                display: none;
                position: absolute;
                left: 0;
                background: rgba(255, 255, 255, 0.98);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 12px;
                margin-top: 8px;
                width: 280px;
                max-height: 350px;
                overflow-y: auto;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
                z-index: 10000;
                animation: slideDown 0.2s ease;
            }}

            .filter-dropdown.open .filter-dropdown-content {{
                display: block;
            }}

            .filter-actions {{
                padding: 12px;
                border-bottom: 1px solid rgba(0, 0, 0, 0.06);
                background: linear-gradient(135deg, #f6f8fb 0%, #e9ecef 100%);
                display: flex;
                gap: 8px;
            }}

            .filter-actions button {{
                background: white;
                border: 1px solid rgba(0, 0, 0, 0.08);
                padding: 6px 12px;
                cursor: pointer;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
                color: #4a5568;
                transition: all 0.2s ease;
                flex: 1;
            }}

            .filter-actions button:hover {{
                background: #003087;
                color: white;
                border-color: #003087;
                transform: translateY(-1px);
            }}

            .filter-apply {{
                padding: 12px;
                border-top: 1px solid rgba(0, 0, 0, 0.06);
                background: linear-gradient(135deg, #f6f8fb 0%, #e9ecef 100%);
                display: flex;
                justify-content: flex-end;
                gap: 8px;
            }}

            .filter-apply button {{
                padding: 8px 16px;
                cursor: pointer;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                border: none;
                transition: all 0.2s ease;
            }}

            .apply-btn {{
                background: linear-gradient(135deg, #003087 0%, #0052CC 100%);
                color: white;
                box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
            }}

            .apply-btn:hover {{
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }}

            .cancel-btn {{
                background: white;
                color: #4a5568;
                border: 1px solid rgba(0, 0, 0, 0.08);
            }}

            .cancel-btn:hover {{
                background: #f7fafc;
                transform: translateY(-1px);
            }}

            .filter-items {{
                padding: 8px;
            }}

            .filter-item {{
                display: block;
                padding: 10px 12px;
                cursor: pointer;
                user-select: none;
                border-radius: 8px;
                transition: all 0.2s ease;
                margin-bottom: 2px;
            }}

            .filter-item:hover {{
                background: linear-gradient(90deg, rgba(102, 126, 234, 0.08) 0%, transparent 100%);
            }}

            .filter-item input[type="checkbox"] {{
                margin-right: 10px;
                cursor: pointer;
                width: 16px;
                height: 16px;
                accent-color: #003087;
            }}

            .filter-item span {{
                color: #2d3748;
                font-size: 13px;
            }}
        </style>

        <div class="filter-panel">
            <div class="filter-title">📊 Filters</div>

            <!-- Year Filter -->
            <div class="filter-dropdown" id="year-dropdown">
                <div class="filter-button" onclick="toggleDropdown('year-dropdown')">
                    Filter by Year
                </div>
                <div class="filter-dropdown-content">
                    <div class="filter-actions">
                        <button onclick="selectAll('year-filter')">Select All</button>
                        <button onclick="deselectAll('year-filter')">Clear</button>
                    </div>
                    <div class="filter-items">
                        {''.join(year_checkboxes)}
                    </div>
                    <div class="filter-apply">
                        <button class="cancel-btn" onclick="closeDropdown('year-dropdown')">Cancel</button>
                        <button class="apply-btn" onclick="applyFiltersAndClose('year-dropdown')">Apply</button>
                    </div>
                </div>
            </div>

            <!-- Pilot Filter -->
            <div class="filter-dropdown" id="pilot-dropdown">
                <div class="filter-button" onclick="toggleDropdown('pilot-dropdown')">
                    Filter by Pilot
                </div>
                <div class="filter-dropdown-content">
                    <div class="filter-actions">
                        <button onclick="selectAll('pilot-filter')">Select All</button>
                        <button onclick="deselectAll('pilot-filter')">Clear</button>
                    </div>
                    <div class="filter-items">
                        {''.join(pilot_checkboxes)}
                    </div>
                    <div class="filter-apply">
                        <button class="cancel-btn" onclick="closeDropdown('pilot-dropdown')">Cancel</button>
                        <button class="apply-btn" onclick="applyFiltersAndClose('pilot-dropdown')">Apply</button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            // Inject track metadata from Python
            var trackMetadata = {json.dumps(track_metadata)};

            // Map from pilot display names to raw names (for filtering)
            // Convert sets to arrays for JSON serialization
            var pilotDisplayToRaw = {json.dumps({k: list(v) for k, v in pilot_display_to_raw.items()})};

            // Store map reference and collected layers
            var mapInstance = null;
            var collectedLayers = [];

            // ====================
            // Dynamic Flight Loading
            // ====================
            var flightLayers = {{}};  // Store flight layers by ID for filtering
            var flightsLoaded = false;

            // Generate color for flight (matches Python color generation)
            function generateFlightColor(index, total) {{
                // Use HSV color space for better distribution
                var hue = (index * 137.508) % 360;  // Golden angle for good distribution
                var saturation = 75;
                var value = 85;

                // Convert HSV to RGB
                var c = value * saturation / 10000;
                var x = c * (1 - Math.abs(((hue / 60) % 2) - 1));
                var m = value / 100 - c;

                var r, g, b;
                if (hue < 60) {{ r = c; g = x; b = 0; }}
                else if (hue < 120) {{ r = x; g = c; b = 0; }}
                else if (hue < 180) {{ r = 0; g = c; b = x; }}
                else if (hue < 240) {{ r = 0; g = x; b = c; }}
                else if (hue < 300) {{ r = x; g = 0; b = c; }}
                else {{ r = c; g = 0; b = x; }}

                r = Math.round((r + m) * 255);
                g = Math.round((g + m) * 255);
                b = Math.round((b + m) * 255);

                return '#' + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
            }}

            // Load and display flights from manifest
            async function loadFlights() {{
                console.log('Loading flights from manifest...');

                try {{
                    // Load manifest
                    const manifestResponse = await fetch('flights_manifest.json');
                    if (!manifestResponse.ok) {{
                        throw new Error('Failed to load flights manifest');
                    }}

                    const manifest = await manifestResponse.json();
                    console.log(`Loaded manifest with ${{manifest.total_flights}} flights`);

                    // Get the flights layer group
                    const flightsGroup = mapInstance._layers[Object.keys(mapInstance._layers).find(
                        key => mapInstance._layers[key].options && mapInstance._layers[key].options.name === 'Individual Flights'
                    )];

                    if (!flightsGroup) {{
                        console.error('Could not find flights layer group');
                        return;
                    }}

                    // Load each flight (in parallel for speed)
                    const flightPromises = manifest.flights.map((flightMeta, index) =>
                        loadFlight(flightMeta, index, manifest.total_flights, flightsGroup)
                    );

                    await Promise.all(flightPromises);

                    flightsLoaded = true;
                    console.log(`Successfully loaded ${{manifest.total_flights}} flights`);

                }} catch (error) {{
                    console.error('Error loading flights:', error);
                }}
            }}

            // Load individual flight data and add to map
            async function loadFlight(flightMeta, index, total, flightsGroup) {{
                try {{
                    const response = await fetch(flightMeta.file);
                    if (!response.ok) {{
                        console.error(`Failed to load ${{flightMeta.file}}`);
                        return;
                    }}

                    const flightData = await response.json();
                    const color = generateFlightColor(flightMeta.color_index, total);

                    // Create popup HTML
                    let popupHtml = `<b>${{flightData.pilot_display_name}}</b><br>`;
                    popupHtml += `Date: <a href="#" onclick="filterByDate('${{flightData.flight_date}}'); return false;" style="color: #003087; text-decoration: underline; cursor: pointer;">${{flightData.flight_date}}</a><br>`;
                    if (flightData.aircraft) popupHtml += `Aircraft: ${{flightData.aircraft}}<br>`;
                    if (flightData.duration) popupHtml += `Duration: ${{flightData.duration}}<br>`;
                    if (flightData.distance_km) popupHtml += `Distance: ${{flightData.distance_km.toFixed(1)}} km<br>`;
                    if (flightData.avg_speed_kmh) popupHtml += `Avg Speed: ${{flightData.avg_speed_kmh.toFixed(1)}} km/h<br>`;
                    if (flightData.points) popupHtml += `Points: ${{flightData.points.toFixed(1)}}<br>`;

                    if (flightData.dsid) {{
                        const olcUrl = `https://www.onlinecontest.org/olc-3.0/gliding/flightinfo.html?dsId=${{flightData.dsid}}&f_map=`;
                        popupHtml += `<small><a href="${{olcUrl}}" target="_blank">${{flightData.filename}}</a></small>`;
                    }} else {{
                        popupHtml += `<small>${{flightData.filename}}</small>`;
                    }}

                    // Create polyline
                    const polyline = L.polyline(flightData.coordinates, {{
                        color: color,
                        weight: 2,
                        opacity: 0.7
                    }})
                    .bindPopup(popupHtml)
                    .bindTooltip(`${{flightData.pilot_display_name}} - ${{flightData.flight_date}}`);

                    // Store flight metadata for filtering
                    polyline.flightMeta = {{
                        year: flightData.year,
                        pilot: flightData.pilot_name,
                        flight_date: flightData.flight_date,
                        id: flightData.id
                    }};

                    flightsGroup.addLayer(polyline);
                    flightLayers[flightData.id] = {{ line: polyline, markers: [] }};

                    // Add start marker (green)
                    if (flightData.coordinates && flightData.coordinates.length > 0) {{
                        const startMarker = L.circleMarker(flightData.coordinates[0], {{
                            radius: 4,
                            color: 'green',
                            fillColor: 'green',
                            fillOpacity: 0.8
                        }}).bindPopup(`<b>Start</b><br>${{flightData.pilot_display_name}}<br>${{flightData.flight_date}}`);

                        startMarker.flightMeta = polyline.flightMeta;
                        flightsGroup.addLayer(startMarker);
                        flightLayers[flightData.id].markers.push(startMarker);

                        // Add end marker (red)
                        const endMarker = L.circleMarker(flightData.coordinates[flightData.coordinates.length - 1], {{
                            radius: 4,
                            color: 'red',
                            fillColor: 'red',
                            fillOpacity: 0.8
                        }}).bindPopup(`<b>End</b><br>${{flightData.pilot_display_name}}<br>${{flightData.flight_date}}`);

                        endMarker.flightMeta = polyline.flightMeta;
                        flightsGroup.addLayer(endMarker);
                        flightLayers[flightData.id].markers.push(endMarker);
                    }}

                }} catch (error) {{
                    console.error(`Error loading flight ${{flightMeta.id}}:`, error);
                }}
            }}

            // Initialize flight loading when map is ready
            window.addEventListener('load', function() {{
                setTimeout(function() {{
                    // Find map instance
                    var mapId = Object.keys(window).find(key => key.startsWith('map_') && window[key] && window[key]._container);
                    if (mapId) {{
                        mapInstance = window[mapId];
                        console.log('Map instance found, loading flights...');
                        loadFlights();
                    }} else {{
                        console.error('Could not find map instance');
                    }}
                }}, 500);
            }});

            // Close dropdowns when clicking outside
            document.addEventListener('click', function(event) {{
                if (!event.target.closest('.filter-dropdown')) {{
                    document.querySelectorAll('.filter-dropdown').forEach(function(dropdown) {{
                        dropdown.classList.remove('open');
                    }});
                }}
            }});

            function toggleDropdown(id) {{
                event.stopPropagation();
                var dropdown = document.getElementById(id);
                var wasOpen = dropdown.classList.contains('open');

                // Close all dropdowns
                document.querySelectorAll('.filter-dropdown').forEach(function(d) {{
                    d.classList.remove('open');
                }});

                // Toggle current dropdown
                if (!wasOpen) {{
                    dropdown.classList.add('open');
                }}
            }}

            function selectAll(className) {{
                event.stopPropagation();
                document.querySelectorAll('.' + className).forEach(function(checkbox) {{
                    checkbox.checked = true;
                }});
            }}

            function deselectAll(className) {{
                event.stopPropagation();
                document.querySelectorAll('.' + className).forEach(function(checkbox) {{
                    checkbox.checked = false;
                }});
            }}

            function closeDropdown(id) {{
                event.stopPropagation();
                var dropdown = document.getElementById(id);
                dropdown.classList.remove('open');
            }}

            function applyFiltersAndClose(id) {{
                event.stopPropagation();
                applyFilters();
                closeDropdown(id);
            }}

            function applyFilters() {{
                if (!mapInstance) {{
                    console.error('Map instance not found');
                    return;
                }}

                if (!flightsLoaded) {{
                    console.log('Flights not yet loaded, waiting...');
                    return;
                }}

                // Get selected years
                var selectedYears = [];
                document.querySelectorAll('.year-filter:checked').forEach(function(cb) {{
                    selectedYears.push(cb.value);
                }});

                // Get selected pilot display names
                var selectedPilotDisplayNames = [];
                document.querySelectorAll('.pilot-filter:checked').forEach(function(cb) {{
                    selectedPilotDisplayNames.push(cb.value);
                }});

                // Convert display names to all corresponding raw names
                var selectedRawPilotNames = [];
                selectedPilotDisplayNames.forEach(function(displayName) {{
                    var rawNames = pilotDisplayToRaw[displayName];
                    if (rawNames) {{
                        selectedRawPilotNames = selectedRawPilotNames.concat(rawNames);
                    }}
                }});

                console.log('Applying filters - Years:', selectedYears, 'Pilot Display Names:', selectedPilotDisplayNames);
                console.log('Mapped to Raw Pilot Names:', selectedRawPilotNames);

                // Keep track of how many layers we show/hide
                var shown = 0;
                var hidden = 0;
                var matched = 0;

                // Loop through dynamically loaded flights
                Object.keys(flightLayers).forEach(function(flightId) {{
                    var flight = flightLayers[flightId];
                    var meta = flight.line.flightMeta;

                    if (!meta) {{
                        console.warn('Flight missing metadata:', flightId);
                        return;
                    }}

                    matched++;

                    // Check if this track matches the filters
                    var yearMatch = selectedYears.indexOf(meta.year) >= 0;
                    var pilotMatch = selectedRawPilotNames.indexOf(meta.pilot) >= 0;

                    // Show/hide flight layers (polyline + markers)
                    var layers = [flight.line].concat(flight.markers);
                    if (yearMatch && pilotMatch) {{
                        layers.forEach(function(layer) {{
                            if (!mapInstance.hasLayer(layer)) {{
                                mapInstance.addLayer(layer);
                                shown++;
                            }}
                        }});
                    }} else {{
                        layers.forEach(function(layer) {{
                            if (mapInstance.hasLayer(layer)) {{
                                mapInstance.removeLayer(layer);
                                hidden++;
                            }}
                        }});
                    }}
                }});

                console.log('Filter applied - Matched:', matched, 'flights, Layers shown:', shown, 'Layers hidden:', hidden);
            }}

            // Store active date filter
            var activeDateFilter = null;

            // Filter by date function - called when clicking on a date in popup
            function filterByDate(dateString) {{
                if (!mapInstance) {{
                    console.error('Map instance not found');
                    return;
                }}

                if (collectedLayers.length === 0) {{
                    console.error('Layers not collected yet - wait for map to load');
                    return;
                }}

                // Prevent infinite loop: if already filtering by this date, skip
                if (activeDateFilter === dateString) {{
                    console.log('Already filtering by date:', dateString);
                    return;
                }}

                console.log('Filtering by date:', dateString);
                activeDateFilter = dateString;

                // Close any open dropdowns
                document.querySelectorAll('.filter-dropdown').forEach(function(dropdown) {{
                    dropdown.classList.remove('open');
                }});

                var shown = 0;
                var hidden = 0;

                // Loop through trackMetadata and show/hide based on date
                for (var i = 0; i < trackMetadata.length; i++) {{
                    var meta = trackMetadata[i];
                    var layerId = meta.layer_id;
                    var layer = window[layerId];

                    if (!layer) {{
                        continue;
                    }}

                    // Check if this track matches the date filter
                    var dateMatch = meta.flight_date === dateString;

                    if (dateMatch) {{
                        if (!mapInstance.hasLayer(layer)) {{
                            mapInstance.addLayer(layer);
                            shown++;
                        }}
                    }} else {{
                        if (mapInstance.hasLayer(layer)) {{
                            mapInstance.removeLayer(layer);
                            hidden++;
                        }}
                    }}
                }}

                console.log('Date filter applied - Shown:', shown, 'Hidden:', hidden);

                // If satellite tiles are available for this date, automatically switch to satellite layer
                if (typeof availableSatelliteDates !== 'undefined' &&
                    availableSatelliteDates.indexOf(dateString) >= 0) {{

                    console.log('Satellite imagery available for', dateString, '- switching to satellite layer');

                    // Auto-switch to satellite layer and update the date
                    if (typeof switchLayer === 'function') {{
                        switchLayer('satellite-dated');
                    }}
                    if (typeof updateSatelliteDate === 'function') {{
                        updateSatelliteDate(dateString);
                    }}
                }} else if (currentLayer === 'satellite-dated') {{
                    // If no satellite imagery for this date but we're on satellite layer, stay on it
                    console.log('No satellite imagery available for', dateString, '- staying on current satellite date');
                }}
            }}

            // Clear date filter
            function clearDateFilter() {{
                console.log('Clearing date filter');
                activeDateFilter = null;

                // Remove the date filter indicator
                var indicator = document.getElementById('date-filter-indicator');
                if (indicator) {{
                    indicator.remove();
                }}

                // Re-apply the normal year/pilot filters
                applyFilters();
            }}

            // Update UI to show which date is being filtered
            function updateDateFilterIndicator(dateString) {{
                // Remove existing indicator if present
                var existing = document.getElementById('date-filter-indicator');
                if (existing) {{
                    existing.remove();
                }}

                // Create new indicator
                var indicator = document.createElement('div');
                indicator.id = 'date-filter-indicator';
                indicator.style.cssText = `
                    position: fixed;
                    top: 220px;
                    left: 16px;
                    background: linear-gradient(135deg, #003087 0%, #0052CC 100%);
                    color: white;
                    padding: 12px 16px;
                    border-radius: 12px;
                    z-index: 9999;
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    font-size: 14px;
                    font-weight: 500;
                    box-shadow: 0 4px 16px rgba(102, 126, 234, 0.3);
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    animation: slideIn 0.3s ease;
                `;

                indicator.innerHTML = `
                    <span>📅 Showing: ${{dateString}}</span>
                    <button onclick="clearDateFilter()" style="
                        background: rgba(255, 255, 255, 0.2);
                        border: none;
                        color: white;
                        padding: 4px 10px;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 12px;
                        font-weight: 600;
                        transition: all 0.2s ease;
                    " onmouseover="this.style.background='rgba(255,255,255,0.3)'" onmouseout="this.style.background='rgba(255,255,255,0.2)'">
                        ✕ Clear
                    </button>
                `;

                document.body.appendChild(indicator);
            }}

            // Wait for filter map to be ready (reuse global waitForMap from layer selector)
            setTimeout(function() {{
                // Wait for map using the same approach as layer selector
                function waitForFilterMap(callback, attempt) {{
                    attempt = attempt || 0;

                    var foundMap = null;
                    for (var key in window) {{
                        try {{
                            if (window[key] && typeof window[key] === 'object' && typeof window[key].eachLayer === 'function') {{
                                foundMap = window[key];
                                break;
                            }}
                        }} catch(e) {{ }}
                    }}

                    if (foundMap) {{
                        callback(foundMap);
                    }} else if (attempt < 20) {{
                        setTimeout(function() {{ waitForFilterMap(callback, attempt + 1); }}, 500);
                    }}
                }}

                waitForFilterMap(function(foundMapInstance) {{
                    mapInstance = foundMapInstance;  // Set global mapInstance
                    console.log('Filter panel - Map instance found');
                    console.log('Track metadata loaded:', trackMetadata.length, 'entries');

                    // Collect all non-tile layers (flight tracks and markers)
                    // We'll collect them in the order they were added to match metadata order
                    mapInstance.eachLayer(function(layer) {{
                        // Skip tile layers and layer control
                        if (!layer._url && layer.options) {{
                            collectedLayers.push(layer);
                        }}
                    }});

                    console.log('Collected', collectedLayers.length, 'track layers');

                    // Verify we have matching counts
                    if (collectedLayers.length !== trackMetadata.length) {{
                        console.warn('Layer count mismatch! Layers:', collectedLayers.length, 'Metadata:', trackMetadata.length);
                    }}

                    // Mark filter panel as initialized
                    initComponents.filterPanel = true;
                    checkAllInitialized();
                }});
            }}, 100);
        </script>
        '''

        flight_map.get_root().html.add_child(folium.Element(filter_html))

    def _auto_generate_satellite_tiles(self, tracks: List[FlightTrack], airport_code: str):
        """
        Automatically generate satellite tiles for flight dates that don't have them yet.

        Args:
            tracks: List of flight tracks
            airport_code: Airport code for the flights
        """
        try:
            # Import here to avoid circular dependency
            from .satellite_tile_generator import SatelliteTileManager

            # Initialize tile manager (uses daily_sat_tiles directory in project root)
            sat_tiles_dir = Path(__file__).parent.parent.parent / 'daily_sat_tiles'
            tile_manager = SatelliteTileManager(sat_tiles_dir)

            # Extract unique flight dates from tracks
            flight_dates = set()
            for track in tracks:
                if track.flight_date and track.flight_date != 'unknown':
                    flight_dates.add(track.flight_date)

            if not flight_dates:
                logger.info("No valid flight dates found, skipping satellite tile generation")
                return

            # Filter to VIIRS-available dates (2012+)
            viirs_dates, pre_viirs_dates = tile_manager.filter_viirs_dates(flight_dates)

            if pre_viirs_dates:
                logger.info(f"Skipping {len(pre_viirs_dates)} pre-VIIRS dates (before 2012-01-19): {sorted(pre_viirs_dates)}")

            if not viirs_dates:
                logger.info("No dates in VIIRS range (2012+), skipping satellite tile generation")
                return

            # Check which dates already have tiles
            existing_dates = tile_manager.get_generated_dates()
            missing_dates = viirs_dates - existing_dates

            if not missing_dates:
                logger.info(f"All {len(viirs_dates)} flight dates already have satellite tiles")
                return

            logger.info(f"Found {len(missing_dates)} flight dates without satellite tiles")
            logger.info(f"Dates: {', '.join(sorted(missing_dates)[:5])}{'...' if len(missing_dates) > 5 else ''}")
            logger.info(f"")
            logger.info(f"Downloading NASA satellite tiles for {len(missing_dates)} dates...")
            logger.info(f"This may take 5-10 minutes per date (~10,000 tiles each)")
            logger.info(f"Estimated time: {len(missing_dates) * 5}-{len(missing_dates) * 10} minutes")
            logger.info(f"")
            logger.info(f"Progress will be shown below:")
            logger.info(f"━" * 60)

            # Call the satellite tile generator script
            script_path = Path(__file__).parent.parent.parent / 'tile_generator' / 'scripts' / 'fetch_nasa_tiles.py'

            if not script_path.exists():
                logger.warning(f"Satellite tile generator script not found at {script_path}")
                logger.warning("Skipping automatic satellite tile generation")
                logger.warning("To generate tiles manually, run:")
                logger.warning(f"  olc-download generate-satellite-tiles --airport-code {airport_code} --all-dates")
                return

            # Build command
            cmd = [
                sys.executable,
                str(script_path),
                '--downloads-dir', str(self.output_dir),
                '--output-dir', str(sat_tiles_dir),
                '--zoom-start', '8',
                '--zoom-end', '9',
                '--dates'
            ]
            cmd.extend(sorted(missing_dates))

            if airport_code:
                cmd.extend(['--airport-code', airport_code])

            # Run the tile generator with real-time output
            result = subprocess.run(cmd)

            if result.returncode == 0:
                logger.info(f"━" * 60)
                logger.info(f"✓ Successfully generated satellite tiles for {len(missing_dates)} dates")
            else:
                logger.warning(f"━" * 60)
                logger.warning(f"Satellite tile generation failed (exit code {result.returncode})")
                logger.warning("Map will still be generated, but satellite imagery may not be available")
                logger.warning("To retry manually, run:")
                logger.warning(f"  olc-download generate-satellite-tiles --airport-code {airport_code} --all-dates")

        except ImportError as e:
            logger.warning(f"Could not import satellite tile manager: {e}")
            logger.warning("Skipping automatic satellite tile generation")
        except Exception as e:
            logger.warning(f"Error during automatic satellite tile generation: {e}")
            logger.warning("Map will still be generated, but satellite imagery may not be available")

    def create_map(
        self,
        airport_code: str,
        tracks: List[FlightTrack],
        output_file: Optional[Path] = None,
        deployment_mode: str = 'local',
        skip_satellite_tiles: bool = False,
    ) -> Path:
        """
        Create an interactive map with all flight tracks

        Args:
            airport_code: Airport code (used in title)
            tracks: List of FlightTrack objects
            output_file: Output HTML file path (default: downloads/AIRPORT_map.html)
            deployment_mode: Deployment mode - 'local' (file:// URLs) or 'static' (relative URLs for R2/CDN)

        Returns:
            Path to generated HTML file
        """
        if not tracks:
            raise ValueError("No tracks to display")

        # Calculate bounding box of all flight tracks to fit the map
        all_coords = []
        for track in tracks:
            all_coords.extend(track.coordinates)

        if not all_coords:
            raise ValueError("No coordinates found in tracks")

        # Find min/max lat/lon to create bounds
        lats = [coord[0] for coord in all_coords]
        lons = [coord[1] for coord in all_coords]

        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Identify which flights have extreme coordinates for debugging
        for track in tracks:
            if track.coordinates:
                track_lats = [c[0] for c in track.coordinates]
                track_min, track_max = min(track_lats), max(track_lats)
                if track_max == max_lat:
                    logger.warning(f"Northernmost point {max_lat:.4f}° in flight: {track.filename}")
                if track_min == min_lat:
                    logger.warning(f"Southernmost point {min_lat:.4f}° in flight: {track.filename}")

        # Calculate center point for initial map position
        center_lat = (min_lat + max_lat) / 2
        center_lon = (min_lon + max_lon) / 2

        # Calculate appropriate zoom level based on latitude span
        # Rough approximation: each zoom level shows ~180/2^zoom degrees of latitude
        lat_span = max_lat - min_lat
        import math
        if lat_span > 0:
            # Add very minimal padding (1% on each side = 2% total)
            lat_span_with_padding = lat_span * 1.02
            # Calculate zoom level (zoom increases as span decreases)
            zoom_level = math.log2(180 / lat_span_with_padding)
            # Round to nearest integer instead of truncating, for tighter fit
            zoom_level = max(1, min(18, round(zoom_level) + 2))  # Clamp between 1 and 18, +2 for balanced view
        else:
            zoom_level = 10

        logger.info(f"Calculated zoom level {zoom_level} for lat span {lat_span:.4f}° (bounds: {min_lat:.4f} to {max_lat:.4f})")

        # Create map with calculated zoom level
        flight_map = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom_level,
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ, TomTom, Intermap, iPC, USGS, FAO, NPS, NRCAN, GeoBase, Kadaster NL, Ordnance Survey, Esri Japan, METI, Esri China (Hong Kong), and the GIS User Community',
        )

        # Note: All base layer switching is handled by the custom layer selector
        # We don't add separate TileLayer objects here

        # Analyze route segments to find popular flight paths
        def rdp_simplify(points, epsilon):
            """
            Ramer-Douglas-Peucker algorithm to simplify a path.
            Reduces GPS noise while preserving route shape.

            Args:
                points: List of (lat, lon) tuples
                epsilon: Distance threshold in degrees (~0.01° ≈ 1km)

            Returns:
                Simplified list of (lat, lon) tuples
            """
            if len(points) < 3:
                return points

            # Find point with maximum distance from line between first and last
            def perpendicular_distance(point, line_start, line_end):
                """Calculate perpendicular distance from point to line"""
                lat, lon = point
                lat1, lon1 = line_start
                lat2, lon2 = line_end

                # Handle vertical line
                if lon2 == lon1:
                    return abs(lon - lon1)

                # Calculate distance
                numerator = abs((lat2 - lat1) * lon - (lon2 - lon1) * lat + lon2 * lat1 - lat2 * lon1)
                denominator = ((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2) ** 0.5
                return numerator / denominator if denominator > 0 else 0

            dmax = 0
            index = 0
            for i in range(1, len(points) - 1):
                d = perpendicular_distance(points[i], points[0], points[-1])
                if d > dmax:
                    index = i
                    dmax = d

            # If max distance is greater than epsilon, recursively simplify
            if dmax > epsilon:
                # Recursive call
                rec_results1 = rdp_simplify(points[:index + 1], epsilon)
                rec_results2 = rdp_simplify(points[index:], epsilon)

                # Build result list
                return rec_results1[:-1] + rec_results2
            else:
                return [points[0], points[-1]]

        def analyze_destination_routes(tracks, waypoints=None, min_flights=4,
                                      airport_lat=42.43, airport_lon=-71.75, airport_radius_km=3):
            """
            Analyze flight tracks to find routes through grid cells.
            Creates routes for grid sequences that 4+ flights pass through.

            Args:
                tracks: List of flight tracks
                waypoints: Unused (kept for compatibility)
                min_flights: Minimum flights for a route
                airport_lat, airport_lon: Airport coordinates
                airport_radius_km: Radius around airport to exclude

            Returns:
                List of dicts with 'coords', 'count', 'track_indices', 'track_info', 'grid_sequence'
            """
            from collections import defaultdict
            import math

            rdp_epsilon = 0.005  # ~0.5km tolerance for simplification

            def calculate_bearing(lat1, lon1, lat2, lon2):
                """Calculate bearing between two points in degrees"""
                lat1_rad = math.radians(lat1)
                lat2_rad = math.radians(lat2)
                dlon_rad = math.radians(lon2 - lon1)

                y = math.sin(dlon_rad) * math.cos(lat2_rad)
                x = math.cos(lat1_rad) * math.sin(lat2_rad) - \
                    math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)

                bearing_rad = math.atan2(y, x)
                bearing_deg = math.degrees(bearing_rad)
                return (bearing_deg + 360) % 360

            def detect_thermaling(coords, min_distance_km=0.3, circle_threshold_deg=40):
                """
                Filter out thermaling sections based on distance and turn rate.
                Simplified version without timestamps - uses distance between
                simplified points as proxy for cruise vs thermal behavior.

                Args:
                    coords: List of (lat, lon) tuples (RDP-simplified)
                    min_distance_km: Minimum distance between points (< this suggests thermaling)
                    circle_threshold_deg: Turn angle indicating circling behavior

                Returns:
                    List of (lat, lon) tuples with thermaling removed
                """
                if len(coords) < 3:
                    return coords

                cruise_points = []

                for i in range(len(coords)):
                    lat, lon = coords[i]
                    keep_point = True

                    # Check distance from previous point (after RDP simplification)
                    if i > 0:
                        prev_lat, prev_lon = coords[i-1]
                        distance_km = self._haversine_distance(prev_lat, prev_lon, lat, lon)

                        # If consecutive simplified points are very close, it's thermaling
                        # RDP keeps points, so small distances between kept points = circling
                        if distance_km < min_distance_km:
                            keep_point = False

                    # Check for circling behavior (high turn rate)
                    if keep_point and i >= 2 and i < len(coords) - 1:
                        lat0, lon0 = coords[i-2]
                        lat1, lon1 = coords[i-1]
                        lat2, lon2 = coords[i]

                        bearing1 = calculate_bearing(lat0, lon0, lat1, lon1)
                        bearing2 = calculate_bearing(lat1, lon1, lat2, lon2)

                        # Calculate turn angle
                        turn = abs(bearing2 - bearing1)
                        if turn > 180:
                            turn = 360 - turn

                        # Sharp turn suggests thermaling
                        if turn > circle_threshold_deg:
                            keep_point = False

                    if keep_point:
                        cruise_points.append((lat, lon))

                return cruise_points

            # Process each flight to find waypoint sequences
            waypoint_proximity_km = 8.0  # 5 miles ≈ 8 km
            logger.info(f"Analyzing {len(tracks)} flights against {len(waypoints)} waypoints")

            flight_waypoint_sequences = []  # List of (track_idx, track, waypoint_sequence, path)

            for track_idx, track in enumerate(tracks):
                coords = track.coordinates
                if len(coords) < 2:
                    continue

                # Apply RDP simplification
                simplified = rdp_simplify(coords, rdp_epsilon)
                if len(simplified) < 2:
                    continue

                # Remove thermaling
                cruise = detect_thermaling(simplified, min_distance_km=0.3, circle_threshold_deg=40)
                if len(cruise) < 2:
                    continue

                # Find which waypoints this flight passes through (in order)
                waypoint_visits = []
                for coord_idx, (lat, lon) in enumerate(cruise):
                    # Skip points near airport
                    if self._haversine_distance(airport_lat, airport_lon, lat, lon) <= airport_radius_km:
                        continue

                    # Check each waypoint
                    for wp in waypoints:
                        wp_lat, wp_lon = wp['lat'], wp['lon']
                        distance = self._haversine_distance(lat, lon, wp_lat, wp_lon)

                        if distance <= waypoint_proximity_km:
                            # Add this waypoint if not already the last one visited
                            # AND if it's far enough from the last waypoint (to avoid waypoint clusters)
                            should_add = True
                            if waypoint_visits:
                                if waypoint_visits[-1]['name'] == wp['name']:
                                    should_add = False
                                else:
                                    # Check distance from last waypoint
                                    last_wp = None
                                    for w in waypoints:
                                        if w['name'] == waypoint_visits[-1]['name']:
                                            last_wp = w
                                            break

                                    if last_wp:
                                        wp_distance = self._haversine_distance(
                                            last_wp['lat'], last_wp['lon'],
                                            wp['lat'], wp['lon']
                                        )
                                        # Skip waypoints closer than 5km to the previous waypoint
                                        if wp_distance < 5.0:
                                            should_add = False

                            if should_add:
                                waypoint_visits.append({
                                    'name': wp['name'],
                                    'coord_idx': coord_idx
                                })
                            break  # Found a waypoint, don't check others for this coord

                # Only keep flights that visit at least 2 waypoints
                if len(waypoint_visits) >= 2:
                    flight_waypoint_sequences.append({
                        'track_idx': track_idx,
                        'track': track,
                        'waypoint_visits': waypoint_visits,
                        'path': cruise
                    })

            logger.info(f"Found {len(flight_waypoint_sequences)} flights visiting 2+ waypoints")

            # Find all contiguous waypoint subsequences (including multi-hop routes)
            waypoint_sequences = defaultdict(lambda: {'count': 0, 'flights': []})

            for flight in flight_waypoint_sequences:
                visits = flight['waypoint_visits']
                # Generate all contiguous subsequences of length 2+
                for start_idx in range(len(visits)):
                    for end_idx in range(start_idx + 1, len(visits)):
                        # Create subsequence from start_idx to end_idx (inclusive)
                        # Use waypoint names as identifiers
                        subsequence = tuple(visit['name'] for visit in visits[start_idx:end_idx + 1])

                        waypoint_sequences[subsequence]['count'] += 1
                        waypoint_sequences[subsequence]['flights'].append({
                            'track_idx': flight['track_idx'],
                            'track': flight['track'],
                            'path': flight['path'],
                            'start_idx': visits[start_idx]['coord_idx'],
                            'end_idx': visits[end_idx]['coord_idx'],
                            'waypoint_visits': visits[start_idx:end_idx + 1]
                        })

            # Create routes for popular waypoint sequences (min_flights threshold)
            # Prefer longer sequences when they exist
            routes = []
            used_sequences = set()

            # Sort by length (longer first) then by count
            sorted_sequences = sorted(
                waypoint_sequences.items(),
                key=lambda x: (len(x[0]), x[1]['count']),
                reverse=True
            )

            for sequence, data in sorted_sequences:
                # Deduplicate flights first (by pilot+date, in case of duplicate files or multiple visits)
                flights = data['flights']
                seen_flights = set()  # Track by (pilot, date) to avoid showing duplicates
                unique_flights = []
                for f in flights:
                    flight_key = (f['track'].pilot_display_name, f['track'].flight_date)
                    if flight_key not in seen_flights:
                        seen_flights.add(flight_key)
                        unique_flights.append(f)

                # Check if we have enough unique flights
                if len(unique_flights) < min_flights:
                    continue

                # Skip if this sequence is a subsequence of an already-added longer route
                # Always prefer longer routes to show complete cross-country paths
                is_subsequence = False
                for existing_route in routes:
                    existing_seq = existing_route['waypoints']  # waypoints is tuple of names

                    # Check if current sequence is a contiguous subsequence of existing route
                    if len(sequence) < len(existing_seq):
                        # Check if sequence appears in existing_seq
                        for i in range(len(existing_seq) - len(sequence) + 1):
                            if existing_seq[i:i+len(sequence)] == sequence:
                                # It's a subsequence - skip it to prefer the longer route
                                is_subsequence = True
                                break
                    if is_subsequence:
                        break

                if is_subsequence:
                    continue

                # Use unique flights for route creation
                flights = unique_flights

                # Collect all path segments through these waypoints
                all_segments = []
                for flight in flights:
                    start_idx = flight['start_idx']
                    end_idx = flight['end_idx']
                    segment = flight['path'][start_idx:end_idx+1]
                    if len(segment) >= 2:
                        all_segments.append(segment)

                # Create representative path using median of most common paths
                if all_segments:
                    # Resample all segments to same length for comparison
                    from statistics import median

                    # Find median length
                    segment_lengths = [len(seg) for seg in all_segments]
                    target_length = int(median(segment_lengths))

                    # Resample each segment to target length
                    resampled_segments = []
                    for segment in all_segments:
                        if len(segment) < 2:
                            continue
                        # Simple linear interpolation to target length
                        resampled = []
                        for i in range(target_length):
                            # Map i to position in original segment
                            t = i / max(1, target_length - 1)
                            idx = t * (len(segment) - 1)
                            idx_low = int(idx)
                            idx_high = min(idx_low + 1, len(segment) - 1)

                            # Interpolate
                            if idx_low == idx_high:
                                resampled.append(segment[idx_low])
                            else:
                                frac = idx - idx_low
                                lat = segment[idx_low][0] * (1 - frac) + segment[idx_high][0] * frac
                                lon = segment[idx_low][1] * (1 - frac) + segment[idx_high][1] * frac
                                resampled.append((lat, lon))
                        resampled_segments.append(resampled)

                    # Compute median path (point by point median)
                    representative_path = []
                    if resampled_segments:
                        for i in range(target_length):
                            lats = [seg[i][0] for seg in resampled_segments if i < len(seg)]
                            lons = [seg[i][1] for seg in resampled_segments if i < len(seg)]
                            if lats and lons:
                                median_lat = median(lats)
                                median_lon = median(lons)
                                representative_path.append((median_lat, median_lon))

                    if len(representative_path) >= 2:
                        # flights is already deduplicated earlier in the loop
                        track_indices = [f['track_idx'] for f in flights]
                        track_info = [{
                            'idx': f['track_idx'],
                            'pilot': f['track'].pilot_display_name,
                            'date': f['track'].flight_date,
                            'filename': f['track'].filename
                        } for f in flights]

                        # sequence is already a tuple of waypoint names
                        routes.append({
                            'coords': representative_path,
                            'count': len(flights),  # Count of unique flights
                            'track_indices': track_indices,
                            'track_info': track_info,
                            'waypoints': sequence,  # Tuple of waypoint names in sequence
                            'hops': len(sequence) - 1  # Number of hops (segments)
                        })

            # Sort by popularity and number of hops
            routes.sort(key=lambda x: (x['count'], x['hops']), reverse=True)

            logger.info(f"Found {len(routes)} waypoint routes (min {min_flights} flights each)")
            if routes:
                route_str = ' → '.join(routes[0]['waypoints'])
                logger.info(f"Most popular route: {route_str} ({routes[0]['count']} flights, {routes[0]['hops']} hops)")

                # Log top 10 longest routes to understand what's being generated
                longest_routes = sorted(routes, key=lambda x: x['hops'], reverse=True)[:10]
                logger.info(f"Top 10 longest routes:")
                for i, route in enumerate(longest_routes, 1):
                    route_str = ' → '.join(route['waypoints'][:3])  # Show first 3 waypoints
                    if len(route['waypoints']) > 3:
                        route_str += f" ... ({len(route['waypoints'])} waypoints)"
                    logger.info(f"  {i}. {route['count']} flights, {route['hops']} hops: {route_str}")

            return routes

        # Parse Sterling waypoints first (needed for waypoint-based routing)
        kmz_file = Path(__file__).parent.parent.parent / 'sterling_waypoints.kmz'
        waypoints = self._parse_sterling_waypoints_kmz(kmz_file)

        # Get flyable routes by connecting waypoints that flights pass through
        # min 4 flights per waypoint-to-waypoint connection
        route_segments = analyze_destination_routes(tracks, waypoints=waypoints, min_flights=4,
                                                   airport_lat=42.43, airport_lon=-71.75,
                                                   airport_radius_km=3)

        # Aggregate popular tasks from IGC task declarations
        def aggregate_popular_tasks(tracks, min_flights=2):
            """
            Analyze tasks from IGC declarations and find popular tasks.

            Args:
                tracks: List of FlightTrack objects
                min_flights: Minimum number of flights for a task to be considered popular

            Returns:
                List of popular tasks with turnpoint sequences and flight counts
            """
            from collections import defaultdict
            import hashlib

            task_signatures = defaultdict(list)  # signature -> list of (track, task)

            for track in tracks:
                if not track.task or not track.task.get('turnpoints'):
                    continue

                turnpoints = track.task['turnpoints']
                if len(turnpoints) < 2:
                    continue

                # Create a signature for this task based on turnpoint sequence
                # Use turnpoint names (normalized) to identify similar tasks
                tp_names = [tp['name'].strip().upper() for tp in turnpoints]
                signature = '->'.join(tp_names)

                task_signatures[signature].append((track, turnpoints))

            # Find tasks flown by multiple pilots
            popular_tasks = []
            for signature, task_list in task_signatures.items():
                if len(task_list) >= min_flights:
                    # Get unique pilots for this task
                    pilots = set(track.pilot_display_name for track, _ in task_list)

                    popular_tasks.append({
                        'signature': signature,
                        'turnpoints': task_list[0][1],  # Use first occurrence
                        'count': len(task_list),
                        'pilots': len(pilots),
                        'pilot_names': sorted(pilots)
                    })

            # Sort by popularity (flight count)
            popular_tasks.sort(key=lambda x: x['count'], reverse=True)

            if popular_tasks:
                logger.info(f"Found {len(popular_tasks)} popular tasks (flown by multiple pilots)")
                for i, task in enumerate(popular_tasks[:5], 1):
                    tp_str = ' → '.join([tp['name'] for tp in task['turnpoints']])
                    logger.info(f"  {i}. {task['count']} flights by {task['pilots']} pilots: {tp_str}")

            return popular_tasks

        popular_tasks = aggregate_popular_tasks(tracks, min_flights=2)

        # Add heatmap layer to show common flight paths
        # Collect all coordinates from all tracks for heatmap (no weights for better slider response)
        # Sterling airport coordinates (approximate)
        sterling_lat, sterling_lon = 42.43, -71.75
        sterling_exclusion_radius = 5  # km - exclude Sterling area entirely

        heatmap_data = []
        for track in tracks:
            # Use all coordinates from each flight
            coords = track.coordinates
            original_count = len(coords)

            # Add coordinates, excluding Sterling area to avoid overwhelming
            for lat, lon in coords:
                distance = self._haversine_distance(sterling_lat, sterling_lon, lat, lon)

                # Skip Sterling area entirely
                if distance > sterling_exclusion_radius:
                    heatmap_data.append([lat, lon])

            # Debug logging for specific flight
            if "Thomas_Van_de_Velde" in track.filename:
                logger.info(f"Heatmap: {track.filename} - {original_count} coords with distance-based weighting")

        # Export heatmap data to external file
        self.export_heatmap_data(heatmap_data, self.output_dir)

        # Add placeholder heatmap layer (data loaded dynamically via JavaScript)
        # Create an empty layer that JavaScript will populate
        placeholder_heatmap = folium.FeatureGroup(name='Flight Path Density')
        placeholder_heatmap.add_to(flight_map)

        # Add JavaScript to load heatmap dynamically
        heatmap_loader_js = '''
        <script>
        // Dynamic heatmap loader
        var heatmapLayer = null;
        var heatmapLoaded = false;

        async function loadHeatmapData() {
            if (heatmapLoaded) return;
            try {
                console.log('Loading heatmap data...');
                const response = await fetch('heatmap.json');
                if (!response.ok) throw new Error('Failed to load heatmap');
                const data = await response.json();

                // Find the main map
                let mainMap = null;
                for (let key in window) {
                    try {
                        if (window[key] && window[key]._leaflet_id && window[key].getCenter) {
                            mainMap = window[key];
                            break;
                        }
                    } catch(e) {}
                }

                if (mainMap && data.coordinates) {
                    // Create heatmap layer
                    heatmapLayer = L.heatLayer(data.coordinates, {
                        minOpacity: 0.3,
                        maxZoom: 13,
                        radius: 18,
                        blur: 20,
                        max: 2.0,
                        gradient: {
                            0.0: 'blue',
                            0.3: 'lime',
                            0.5: 'yellow',
                            0.7: 'orange',
                            1.0: 'red'
                        }
                    });

                    // Don't add to map by default - let layer control handle it
                    // heatmapLayer.addTo(mainMap);

                    heatmapLoaded = true;
                    console.log('Heatmap loaded:', data.coordinates.length, 'points');

                    // Add to layer control if it exists
                    if (mainMap._layers) {
                        // Find the layer control and add our heatmap
                        Object.values(mainMap._layers).forEach(layer => {
                            if (layer._map === mainMap && heatmapLayer && !mainMap.hasLayer(heatmapLayer)) {
                                // Layer will be controlled by Leaflet's layer control
                            }
                        });
                    }
                }
            } catch (error) {
                console.error('Error loading heatmap:', error);
            }
        }

        // Load heatmap when page loads (but don't add to map automatically)
        window.addEventListener('load', function() {
            setTimeout(loadHeatmapData, 1000);
        });
        </script>
        '''
        flight_map.get_root().html.add_child(folium.Element(heatmap_loader_js))

        # Add popular route segments as polylines with logarithmic scaling
        import math
        route_group = folium.FeatureGroup(name='Popular Segments', show=True)

        # Find min and max counts for logarithmic scaling
        if route_segments:
            counts = [seg['count'] for seg in route_segments]
            min_count = min(counts)
            max_count = max(counts)
        else:
            min_count = max_count = 1

        for route_idx, segment in enumerate(route_segments):
            coords = segment['coords']
            count = segment['count']
            track_indices = segment.get('track_indices', [])
            track_info = segment.get('track_info', [])
            waypoint_names = segment.get('waypoints', None)

            # Logarithmic scaling for color intensity
            # This keeps low-traffic routes visible while showing high-traffic ones
            if max_count > min_count:
                # Log scale normalized to 0-1
                log_intensity = (math.log(count) - math.log(min_count)) / (math.log(max_count) - math.log(min_count))
            else:
                log_intensity = 0.5

            # Color based on logarithmic intensity with more gradations (8 bands)
            if log_intensity < 0.125:
                color = '#003087'  # GBSC Blue (very low traffic)
            elif log_intensity < 0.25:
                color = '#3B82F6'  # Blue (low traffic)
            elif log_intensity < 0.375:
                color = '#06B6D4'  # Cyan (moderate-low)
            elif log_intensity < 0.5:
                color = '#10B981'  # Green (moderate)
            elif log_intensity < 0.625:
                color = '#84CC16'  # Lime (moderate-high)
            elif log_intensity < 0.75:
                color = '#F59E0B'  # Orange (high)
            elif log_intensity < 0.875:
                color = '#F97316'  # Dark orange (very high)
            else:
                color = '#EF4444'  # Red (extremely high traffic)

            # Power curve for line weight to compress high-traffic segments
            # Using square root to reduce dominance of high-traffic routes
            # Weight range: 2-5.5px (reduced from 2-7px)
            weight = 2 + (log_intensity ** 0.6) * 3.5

            # Opacity scales but caps lower to prevent dominance
            # Range: 0.45-0.70 (reduced from 0.5-0.8)
            opacity = 0.45 + log_intensity * 0.25

            # Create detailed popup with flight list and toggle
            flights_list_html = '<div style="max-height: 150px; overflow-y: auto; margin-top: 8px;">'
            for info in track_info[:10]:  # Show first 10
                flights_list_html += f'<div style="font-size: 11px; padding: 2px 0; color: #4A5568;">{info["pilot"]} - {info["date"]}</div>'
            if len(track_info) > 10:
                flights_list_html += f'<div style="font-size: 11px; color: #718096; font-style: italic;">...and {len(track_info) - 10} more</div>'
            flights_list_html += '</div>'

            track_indices_json = str(track_indices).replace("'", '"')

            # Create route title with waypoint names if available
            if waypoint_names:
                route_title = ' → '.join(waypoint_names)
                hops = len(waypoint_names) - 1
                if hops > 1:
                    route_title += f" ({hops} hops)"
            else:
                route_title = f"Route {route_idx + 1}"

            popup_html = f'''
            <div style="
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                min-width: 280px;
                max-width: 350px;
                user-select: none;
            ">
                <div style="
                    font-size: 15px;
                    font-weight: 600;
                    margin-bottom: 8px;
                    color: {color};
                    line-height: 1.3;
                ">
                    {route_title}
                </div>
                <div style="font-size: 14px; margin-bottom: 8px; color: #2D3748;">
                    <b>{count} flights</b> use this segment
                </div>
                <button onclick="toggleRouteFlights({route_idx}, {track_indices_json})" style="
                    background: {color};
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 13px;
                    font-weight: 500;
                    width: 100%;
                    margin-bottom: 8px;
                    transition: opacity 0.2s;
                " onmouseover="this.style.opacity='0.8'" onmouseout="this.style.opacity='1'">
                    <span id="route-toggle-text-{route_idx}">Show Flights</span>
                </button>
                {flights_list_html}
            </div>
            '''

            # Create polyline for this segment using actual GPS coordinates
            folium.PolyLine(
                locations=coords,
                color=color,
                weight=weight,
                opacity=opacity,
                popup=folium.Popup(popup_html, max_width=300)
            ).add_to(route_group)

        route_group.add_to(flight_map)
        logger.info(f"Added {len(route_segments)} popular route segments to map")
        logger.info(f"Route traffic range: {min_count}-{max_count} flights per segment")

        # Add Sterling waypoints from KMZ file
        kmz_file = Path(__file__).parent.parent.parent / 'sterling_waypoints.kmz'
        waypoints = self._parse_sterling_waypoints_kmz(kmz_file)
        if waypoints:
            waypoint_group = folium.FeatureGroup(name='Sterling Waypoints')

            # Define icon styles for each waypoint type
            icon_config = {
                'home': {
                    'icon': '🏠',
                    'color': '#E53E3E',  # red
                    'type_label': 'Home Field'
                },
                'airport': {
                    'icon': '✈️',
                    'color': '#3182CE',  # blue
                    'type_label': 'Airport'
                },
                'landmark': {
                    'icon': '📍',
                    'color': '#38A169',  # green
                    'type_label': 'Landmark'
                },
                'other': {
                    'icon': '⭕',
                    'color': '#718096',  # gray
                    'type_label': 'Waypoint'
                },
                'default': {
                    'icon': '📌',
                    'color': '#003087',  # GBSC blue
                    'type_label': 'Waypoint'
                }
            }

            for idx, wp in enumerate(waypoints):
                wp_type = wp.get('type', 'other')
                config = icon_config.get(wp_type, icon_config['other'])

                # Create custom small icon using DivIcon
                icon_html = f'''
                <div style="
                    font-size: 14px;
                    text-align: center;
                    line-height: 1;
                    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
                    filter: drop-shadow(0 1px 2px rgba(0,0,0,0.2));
                ">{config['icon']}</div>
                '''

                # Create minimal loading placeholder popup (content loaded on-demand)
                popup_html = f'<div id="waypoint_popup_loading_{idx}" style="padding: 20px; text-align: center;">Loading...</div>'

                # Create marker with simple placeholder popup
                # Actual content will be loaded via JavaScript when clicked
                marker = folium.Marker(
                    location=[wp['lat'], wp['lon']],
                    popup=folium.Popup(
                        popup_html,
                        max_width=400,
                        autoPanPaddingTopLeft=[380, 120],
                        autoPanPaddingBottomRight=[20, 20]
                    ),
                    tooltip=wp['name'],
                    icon=folium.DivIcon(html=icon_html)
                )

                # Store waypoint ID for popup loading
                marker.options['waypoint_id'] = f'waypoint_{idx}'

                # Add the marker to the group
                marker.add_to(waypoint_group)

            waypoint_group.add_to(flight_map)
            logger.info(f"Added {len(waypoints)} Sterling waypoints to map (popups load on-demand)")

            # Export waypoint data to external file
            self.export_waypoint_data(waypoints, self.output_dir)

            # Add on-demand waypoint popup loader
            waypoint_loader_js = '''
            <script>
            // On-demand waypoint popup loader
            var waypointData = null;
            var loadedPopups = {};

            async function loadWaypointData() {
                if (waypointData) return waypointData;
                try {
                    const response = await fetch('waypoints.json');
                    if (!response.ok) throw new Error('Failed to load waypoints');
                    const data = await response.json();
                    waypointData = data.waypoints;
                    console.log('Loaded', waypointData.length, 'waypoints');
                    return waypointData;
                } catch (error) {
                    console.error('Error loading waypoints:', error);
                    return null;
                }
            }

            function renderWaypointPopup(wp, idx) {
                return `<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; min-width: 340px; max-width: 380px;">
                    <div style="background: linear-gradient(135deg, ${wp.color}F5 0%, ${wp.color}E0 100%); color: white; padding: 16px 20px; margin: -20px -20px 16px -20px; border-radius: 8px 8px 0 0;">
                        <div style="font-size: 18px; font-weight: 600; margin-bottom: 4px;">${wp.name}</div>
                        <div style="font-size: 12px; opacity: 0.92;"><span style="font-size: 14px;">${wp.icon}</span> <span>${wp.type_label}</span></div>
                    </div>
                    <div style="padding: 0 4px 8px;">
                        <div style="background: #FAFBFC; border-radius: 6px; padding: 11px 13px; margin-bottom: 10px; font-size: 12.5px; line-height: 1.5;">${wp.description}</div>
                        <div style="background: #F9FAFB; border-radius: 6px; padding: 10px 12px;">
                            <div style="font-size: 10px; font-weight: 600; color: #6B7280; margin-bottom: 5px;">📍 COORDINATES</div>
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <span id="coords_${idx}" style="font-family: monospace; font-size: 13px; background: white; padding: 5px 10px; border-radius: 4px;">${wp.lat.toFixed(5)}°, ${wp.lon.toFixed(5)}°</span>
                                <button onclick="navigator.clipboard.writeText(document.getElementById('coords_${idx}').textContent); this.textContent='✓'; setTimeout(()=>this.textContent='📋',1500);" style="background:#3B82F6;color:white;border:none;border-radius:4px;padding:5px 10px;cursor:pointer;margin-left:6px;">📋</button>
                            </div>
                        </div>
                        <div style="background: #FAFBFC; border-radius: 6px; padding: 10px; margin-top: 10px;">
                            <div style="font-size: 11px; font-weight: 600; color: #6B7280; margin-bottom: 8px;"><span>🛰️</span> SATELLITE VIEW</div>
                            <div id="minimap_${idx}" style="width:100%;height:180px;border-radius:4px;background:#F3F4F6;"></div>
                        </div>
                    </div>
                </div>`;
            }

            function initWaypointMinimap(wp, idx) {
                const minimapId = 'minimap_' + idx;
                const minimapDiv = document.getElementById(minimapId);
                if (!minimapDiv || loadedPopups[minimapId]) return;
                try {
                    const minimap = L.map(minimapId, {center:[wp.lat,wp.lon],zoom:16,zoomControl:false,dragging:true,scrollWheelZoom:false,doubleClickZoom:false,boxZoom:false,keyboard:false,tap:false});
                    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19}).addTo(minimap);
                    L.circleMarker([wp.lat,wp.lon],{radius:6,fillColor:wp.color,color:'white',weight:2,fillOpacity:0.9}).addTo(minimap);
                    L.control.zoom({position:'topright'}).addTo(minimap);
                    loadedPopups[minimapId]=true;
                    setTimeout(()=>minimap.invalidateSize(),10);
                } catch(e) {
                    console.error('Error creating minimap:',e);
                    minimapDiv.innerHTML='<div style="padding:20px;text-align:center;color:#718096;">Satellite view unavailable</div>';
                }
            }

            window.addEventListener('load',function(){
                let mainMap=null;
                for(let key in window){try{if(window[key]&&window[key]._leaflet_id&&window[key].getCenter){mainMap=window[key];break;}}catch(e){}}
                if(mainMap){
                    mainMap.on('popupopen',async function(e){
                        const popup=e.popup;
                        const popupContent=popup.getContent();
                        if(popupContent&&popupContent.includes('waypoint_popup_loading_')){
                            const match=popupContent.match(/waypoint_popup_loading_(\\d+)/);
                            if(match){
                                const idx=parseInt(match[1]);
                                const waypoints=await loadWaypointData();
                                if(waypoints&&waypoints[idx]){
                                    const wp=waypoints[idx];
                                    popup.setContent(renderWaypointPopup(wp,idx));
                                    popup.update();
                                    setTimeout(()=>initWaypointMinimap(wp,idx),100);
                                }
                            }
                        }
                    });
                    console.log('Waypoint on-demand popup loader initialized');
                }
            });
            </script>
            '''
            flight_map.get_root().html.add_child(folium.Element(waypoint_loader_js))

            # Add custom CSS for popup styling
            popup_css = '''
            <style>
                    /* Fix close button positioning and styling */
                    .leaflet-popup-close-button {
                        position: absolute !important;
                        top: 8px !important;
                        right: 8px !important;
                        width: 24px !important;
                        height: 24px !important;
                        padding: 0 !important;
                        border: none !important;
                        background: rgba(255, 255, 255, 0.9) !important;
                        border-radius: 50% !important;
                        font-size: 18px !important;
                        line-height: 22px !important;
                        color: #374151 !important;
                        text-align: center !important;
                        display: flex !important;
                        align-items: center !important;
                        justify-content: center !important;
                        cursor: pointer !important;
                        z-index: 1000 !important;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
                        transition: all 0.2s ease !important;
                    }

                    .leaflet-popup-close-button:hover {
                        background: rgba(255, 255, 255, 1) !important;
                        color: #EF4444 !important;
                        transform: scale(1.1) !important;
                    }

                    /* Ensure popup content wrapper respects padding and has proper border radius */
                    .leaflet-popup-content-wrapper {
                        border-radius: 8px !important;
                        overflow: hidden !important;
                        padding: 0 !important;
                    }

                    .leaflet-popup-content {
                        margin: 20px !important;
                        overflow: visible !important;
                    }

                    /* Ensure popups have proper z-index */
                    .leaflet-popup-pane {
                        z-index: 700 !important;
                    }
                </style>
                '''
            flight_map.get_root().html.add_child(folium.Element(popup_css))

        # Add popular tasks visualization
        if popular_tasks:
            task_group = folium.FeatureGroup(name='Declared Tasks')

            # Color scheme for tasks (distinct from routes)
            task_colors = ['#003087', '#EC4899', '#10B981', '#F59E0B', '#3B82F6']  # GBSC Blue, Pink, Green, Orange, Light Blue

            for task_idx, task in enumerate(popular_tasks):
                color = task_colors[task_idx % len(task_colors)]
                turnpoints = task['turnpoints']

                # Create task line connecting all turnpoints
                task_coords = [(tp['lat'], tp['lon']) for tp in turnpoints]

                # Create popup with task details
                tp_list = '<br>'.join([f"{i+1}. {tp['name']}" for i, tp in enumerate(turnpoints)])
                popup_html = f'''
                <div style="font-family: sans-serif; min-width: 200px;">
                    <div style="font-weight: bold; font-size: 14px; margin-bottom: 8px; color: {color};">
                        🎯 Popular Task
                    </div>
                    <div style="font-size: 12px; margin-bottom: 10px;">
                        <strong>Turnpoints ({len(turnpoints)}):</strong><br>
                        {tp_list}
                    </div>
                    <div style="font-size: 11px; color: #666; border-top: 1px solid #ddd; padding-top: 6px;">
                        Flown {task['count']} times by {task['pilots']} pilot(s)<br>
                        <em>{', '.join(task['pilot_names'][:3])}{' ...' if len(task['pilot_names']) > 3 else ''}</em>
                    </div>
                </div>
                '''

                # Add task polyline
                folium.PolyLine(
                    task_coords,
                    color=color,
                    weight=4,
                    opacity=0.8,
                    popup=folium.Popup(
                        popup_html,
                        max_width=300,
                        min_width=200,
                        max_height=400
                    ),
                    tooltip=f"Task: {' → '.join([tp['name'] for tp in turnpoints[:3]])}{'...' if len(turnpoints) > 3 else ''}"
                ).add_to(task_group)

                # Add markers for each turnpoint
                for tp_idx, tp in enumerate(turnpoints):
                    # Different marker for start and finish
                    if tp_idx == 0:
                        icon_html = f'''
                        <div style="
                            background-color: {color};
                            border: 2px solid white;
                            border-radius: 50%;
                            width: 20px;
                            height: 20px;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            color: white;
                            font-size: 12px;
                            font-weight: bold;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                        ">S</div>
                        '''
                    elif tp_idx == len(turnpoints) - 1:
                        icon_html = f'''
                        <div style="
                            background-color: {color};
                            border: 2px solid white;
                            border-radius: 50%;
                            width: 20px;
                            height: 20px;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            color: white;
                            font-size: 12px;
                            font-weight: bold;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                        ">F</div>
                        '''
                    else:
                        icon_html = f'''
                        <div style="
                            background-color: {color};
                            border: 2px solid white;
                            border-radius: 50%;
                            width: 16px;
                            height: 16px;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
                        "></div>
                        '''

                    folium.Marker(
                        location=[tp['lat'], tp['lon']],
                        icon=folium.DivIcon(html=icon_html),
                        tooltip=tp['name']
                    ).add_to(task_group)

            task_group.add_to(flight_map)
            logger.info(f"Added {len(popular_tasks)} popular tasks to map")

        # Organize tracks by year and pilot for filtering
        from collections import defaultdict
        tracks_by_year = defaultdict(list)
        tracks_by_pilot_display = defaultdict(list)  # Group by cleaned display name
        pilot_display_to_raw = defaultdict(set)  # Map cleaned name to all raw names

        for track in tracks:
            tracks_by_year[track.year].append(track)
            # Group by display name (cleaned) instead of raw name
            tracks_by_pilot_display[track.pilot_display_name].append(track)
            # Track mapping from display name to raw names for filtering
            pilot_display_to_raw[track.pilot_display_name].add(track.pilot_name)

        # Create FeatureGroup for individual flight tracks (toggleable layer)
        flights_group = folium.FeatureGroup(name='Individual Flights', show=True)
        flights_group.add_to(flight_map)  # Add to map immediately

        # NOTE: Flight tracks are NOT added to the map here - they will be loaded dynamically
        # from separate JSON files to keep HTML file small. See flights_manifest.json.

        # Build minimal track metadata for filtering (no coordinates)
        track_metadata = []
        for i, track in enumerate(tracks):
            # Store metadata for this track (will be used by JavaScript for filtering)
            track_metadata.append({
                'flight_id': f"flight_{i:04d}",
                'year': track.year,
                'pilot': track.pilot_name,
                'pilot_display_name': track.pilot_display_name,
                'flight_date': track.flight_date,
                'type': 'line'
            })

        logger.info(f"Prepared metadata for {len(tracks)} flight tracks (coordinates in separate JSON files)")

        # Add title
        num_years = len(tracks_by_year)
        num_pilots = len(tracks_by_pilot_display)
        title_html = f'''
        <style>
            .title-and-toggle-container {{
                position: fixed;
                top: 16px;
                left: 16px;
                z-index: 9999;
                display: flex;
                gap: 12px;
                align-items: flex-start;
                pointer-events: none;
            }}

            .map-title-card {{
                width: auto;
                max-width: 600px;
                background: rgba(255, 255, 255, 0.98);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 16px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
                padding: 20px 24px;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                pointer-events: auto;
            }}

            .heatmap-toggle-btn {{
                background: rgba(255, 255, 255, 0.98);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 24px;
                padding: 10px 18px;
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 14px;
                font-weight: 500;
                color: #4a5568;
                cursor: pointer;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
                gap: 8px;
                user-select: none;
                pointer-events: auto;
            }}

            .heatmap-toggle-btn:hover {{
                transform: translateY(-1px);
                box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
                border-color: rgba(102, 126, 234, 0.3);
            }}

            .heatmap-toggle-btn.active {{
                background: linear-gradient(135deg, #003087 0%, #0052CC 100%);
                color: white;
                border-color: transparent;
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }}

            .heatmap-toggle-btn.active:hover {{
                box-shadow: 0 6px 16px rgba(102, 126, 234, 0.5);
            }}

            .heatmap-icon {{
                font-size: 16px;
            }}

            .map-title-header {{
                font-size: 24px;
                font-weight: 700;
                background: linear-gradient(135deg, #003087 0%, #0052CC 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 12px;
                letter-spacing: -0.5px;
            }}

            .map-title-stats {{
                display: flex;
                gap: 20px;
                margin-bottom: 12px;
                flex-wrap: wrap;
            }}

            .map-stat {{
                display: flex;
                align-items: center;
                gap: 6px;
                color: #4a5568;
                font-size: 14px;
                font-weight: 500;
            }}

            .map-stat-value {{
                color: #2d3748;
                font-weight: 600;
                font-size: 15px;
            }}

            .map-title-tips {{
                color: #718096;
                font-size: 12px;
                line-height: 1.6;
                margin-top: 8px;
                padding-top: 12px;
                border-top: 1px solid rgba(0, 0, 0, 0.06);
            }}

            .map-title-tips div {{
                display: flex;
                align-items: center;
                gap: 6px;
                margin-bottom: 4px;
            }}

            .tip-icon {{
                color: #003087;
                font-size: 14px;
            }}
        </style>

        <!-- Loading overlay -->
        <div class="loading-overlay" id="loadingOverlay">
            <div class="loading-spinner"></div>
            <div class="loading-text">Loading Sterling Flights</div>
            <div class="loading-subtext">Initializing map and flight data...</div>
            <div class="loading-progress" id="loadingProgress">
                <div class="progress-counter">
                    <span id="loadedCount">0</span> / <span id="totalCount">0</span> flight tracks
                </div>
                <div class="progress-bar-container">
                    <div class="progress-bar" id="progressBar"></div>
                </div>
            </div>
        </div>

        <div class="title-and-toggle-container">
            <div class="map-title-card">
                <div class="map-title-header">Sterling Flights</div>
                <div class="map-title-stats">
                    <div class="map-stat">
                        <span>✈️</span>
                        <span class="map-stat-value">{len(tracks)}</span>
                        <span>flights</span>
                    </div>
                    <div class="map-stat">
                        <span>👥</span>
                        <span class="map-stat-value">{num_pilots}</span>
                        <span>pilots</span>
                    </div>
                    <div class="map-stat">
                        <span>📅</span>
                        <span class="map-stat-value">{num_years}</span>
                        <span>years</span>
                    </div>
                </div>
                <div class="map-title-tips">
                    <div><span class="tip-icon">🗺️</span> Use layer selector to change map style</div>
                    <div><span class="tip-icon">✈️</span> Toggle flights, heatmap, and waypoints</div>
                    <div><span class="tip-icon">📊</span> Filter flights by year or pilot</div>
                </div>
            </div>

            <div class="heatmap-toggle-btn" id="flightTracksToggleBtn" onclick="toggleFlightTracksButton()">
                <span class="heatmap-icon">✈️</span>
                <span>Flights</span>
            </div>

            <div class="heatmap-toggle-btn active" id="routesToggleBtn" onclick="toggleRoutesButton()">
                <span class="heatmap-icon">🛤️</span>
                <span>Segments</span>
            </div>

            <div class="heatmap-toggle-btn" id="heatmapToggleBtn" onclick="toggleHeatmapButton()">
                <span class="heatmap-icon">🔥</span>
                <span>Heatmap</span>
            </div>

            <div class="heatmap-toggle-btn" id="waypointToggleBtn" onclick="toggleWaypointButton()">
                <span class="heatmap-icon">📍</span>
                <span>Waypoints</span>
            </div>

            <div class="heatmap-toggle-btn" id="tasksToggleBtn" onclick="toggleTasksButton()">
                <span class="heatmap-icon">🎯</span>
                <span>Tasks</span>
            </div>
        </div>

        <script>
            // Standalone heatmap toggle implementation
            var heatmapBtnMapInstance = null;
            var heatmapBtnLayer = null;
            var heatmapBtnVisible = false;  // Start hidden, routes are default

            // Routes toggle variables
            var routesBtnMapInstance = null;
            var routesBtnLayer = null;
            var routesBtnVisible = true;  // Start visible

            // Waypoint toggle variables
            var waypointBtnMapInstance = null;
            var waypointBtnLayer = null;
            var waypointBtnVisible = false;

            // Initialize heatmap toggle - wait for map to be ready
            setTimeout(function() {{
                function waitForHeatmapMap(callback, attempt) {{
                    attempt = attempt || 0;
                    var foundMap = null;
                    for (var key in window) {{
                        try {{
                            if (window[key] && typeof window[key] === 'object' && typeof window[key].eachLayer === 'function') {{
                                foundMap = window[key];
                                break;
                            }}
                        }} catch(e) {{ }}
                    }}
                    if (foundMap) {{
                        callback(foundMap);
                    }} else if (attempt < 20) {{
                        setTimeout(function() {{ waitForHeatmapMap(callback, attempt + 1); }}, 500);
                    }}
                }}

                waitForHeatmapMap(function(mapInstance) {{
                    heatmapBtnMapInstance = mapInstance;
                    console.log('Heatmap - Map instance found');

                    var layerNum = 0;
                    // Find heatmap layer - check all layers and log their types
                    heatmapBtnMapInstance.eachLayer(function(layer) {{
                        layerNum++;

                        // Check for various heatmap indicators
                        var isHeatmap = false;

                        // Check for HeatLayer properties
                        if (layer._canvas) {{
                            console.log('Layer', layerNum, 'has _canvas (likely heatmap)');
                            isHeatmap = true;
                        }}
                        if (layer._heat) {{
                            console.log('Layer', layerNum, 'has _heat');
                            isHeatmap = true;
                        }}
                        // Check if it's a FeatureGroup that might contain heatmap
                        if (layer._layers && !layer._url) {{
                            // It's a group layer, check its children
                            var hasHeatChild = false;
                            for (var childId in layer._layers) {{
                                var child = layer._layers[childId];
                                if (child._canvas || child._heat) {{
                                    console.log('Layer', layerNum, 'is a group containing heatmap');
                                    isHeatmap = true;
                                    heatmapBtnLayer = child; // Use the actual heatmap child
                                    break;
                                }}
                            }}
                        }}

                        if (isHeatmap && !heatmapBtnLayer) {{
                            heatmapBtnLayer = layer;
                            console.log('Found heatmap layer:', layer);
                        }}
                    }});

                    if (heatmapBtnLayer) {{
                        // Hide it initially (routes are default)
                        heatmapBtnMapInstance.removeLayer(heatmapBtnLayer);
                        console.log('Heatmap layer found, starting hidden');
                        }} else {{
                            console.error('Heatmap layer not found after checking', layerNum, 'layers');
                        }}

                    // Mark heatmap toggle as initialized
                    initComponents.heatmapToggle = true;
                    checkAllInitialized();
                    }});
            }}, 100);

            // Initialize routes toggle - wait for map to be ready
            setTimeout(function() {{
                function waitForRoutesMap(callback, attempt) {{
                    attempt = attempt || 0;
                    var foundMap = null;
                    for (var key in window) {{
                        try {{
                            if (window[key] && typeof window[key] === 'object' && typeof window[key].eachLayer === 'function') {{
                                foundMap = window[key];
                                break;
                            }}
                        }} catch(e) {{ }}
                    }}
                    if (foundMap) {{
                        callback(foundMap);
                    }} else if (attempt < 20) {{
                        setTimeout(function() {{ waitForRoutesMap(callback, attempt + 1); }}, 500);
                    }}
                }}

                waitForRoutesMap(function(mapInstance) {{
                    routesBtnMapInstance = mapInstance;
                    console.log('Routes - Map instance found');

                    var layerNum = 0;
                    // Find routes FeatureGroup by detecting polylines
                    routesBtnMapInstance.eachLayer(function(layer) {{
                        layerNum++;

                        // Check if it's a FeatureGroup with polylines (routes)
                        if (layer._layers && !layer._url) {{
                            var childCount = Object.keys(layer._layers).length;

                            // Check if children are polylines (routes) vs markers (waypoints)
                            var hasPolylines = false;
                            var hasMarkers = false;

                            for (var childId in layer._layers) {{
                                var child = layer._layers[childId];
                                if (child._latlngs && child._latlngs.length > 0) {{
                                    // It's a polyline
                                    hasPolylines = true;
                                }}
                                if (child._icon || child._latlng) {{
                                    // It's a marker
                                    hasMarkers = true;
                                }}
                            }}

                            console.log('Layer', layerNum, 'FeatureGroup with', childCount, 'children - polylines:', hasPolylines, 'markers:', hasMarkers);

                            // Routes layer has polylines but not markers
                            if (hasPolylines && !hasMarkers && childCount < 200) {{
                                routesBtnLayer = layer;
                                console.log('Found Popular Routes layer with', childCount, 'route segments');
                            }}
                        }}
                    }});

                    if (routesBtnLayer) {{
                        // Keep it visible initially (routes are default)
                        console.log('Routes layer found, starting visible');
                    }} else {{
                        console.error('Routes layer not found after checking', layerNum, 'layers');
                    }}

                    // Mark routes toggle as initialized
                    initComponents.routesToggle = true;
                    checkAllInitialized();
                }});
            }}, 100);

            function toggleRoutesButton() {{
                console.log('Routes button clicked');

                if (!routesBtnMapInstance || !routesBtnLayer) {{
                    console.error('Map or routes layer not ready yet');
                    return;
                }}

                var btn = document.getElementById('routesToggleBtn');
                routesBtnVisible = !routesBtnVisible;

                if (routesBtnVisible) {{
                    routesBtnMapInstance.addLayer(routesBtnLayer);
                    btn.classList.add('active');
                    console.log('Routes turned ON');
                }} else {{
                    routesBtnMapInstance.removeLayer(routesBtnLayer);
                    btn.classList.remove('active');
                    console.log('Routes turned OFF');
                }}
            }}

            function toggleHeatmapButton() {{
                console.log('Heatmap button clicked');

                if (!heatmapBtnMapInstance || !heatmapBtnLayer) {{
                    console.error('Map or heatmap layer not ready yet');
                    return;
                }}

                var btn = document.getElementById('heatmapToggleBtn');
                heatmapBtnVisible = !heatmapBtnVisible;

                if (heatmapBtnVisible) {{
                    heatmapBtnMapInstance.addLayer(heatmapBtnLayer);
                    btn.classList.add('active');
                    console.log('Heatmap turned ON');
                }} else {{
                    heatmapBtnMapInstance.removeLayer(heatmapBtnLayer);
                    btn.classList.remove('active');
                    console.log('Heatmap turned OFF');
                }}
            }}

            // Initialize waypoint toggle - wait for map to be ready
            setTimeout(function() {{
                function waitForWaypointMap(callback, attempt) {{
                    attempt = attempt || 0;
                    var foundMap = null;
                    for (var key in window) {{
                        try {{
                            if (window[key] && typeof window[key] === 'object' && typeof window[key].eachLayer === 'function') {{
                                foundMap = window[key];
                                break;
                            }}
                        }} catch(e) {{ }}
                    }}
                    if (foundMap) {{
                        callback(foundMap);
                    }} else if (attempt < 20) {{
                        setTimeout(function() {{ waitForWaypointMap(callback, attempt + 1); }}, 500);
                    }}
                }}

                waitForWaypointMap(function(mapInstance) {{
                    waypointBtnMapInstance = mapInstance;
                    console.log('Waypoint - Map instance found');

                    var layerNum = 0;
                    // Find waypoint FeatureGroup - look for feature groups with markers
                    waypointBtnMapInstance.eachLayer(function(layer) {{
                        layerNum++;

                        // Check if it's a FeatureGroup with the right name
                        if (layer._layers && layer.options && layer.options.name === 'Sterling Waypoints') {{
                            waypointBtnLayer = layer;
                            console.log('Found waypoint layer by name at layer', layerNum);
                        }}

                        // Also check if it's a FeatureGroup with many markers (fallback detection)
                        if (!waypointBtnLayer && layer._layers && Object.keys(layer._layers).length > 100) {{
                            // Check if first child is a marker with DivIcon
                            var firstChild = layer._layers[Object.keys(layer._layers)[0]];
                            if (firstChild && firstChild.options && firstChild.options.icon && firstChild.options.icon.options && firstChild.options.icon.options.html) {{
                                // This is likely our waypoint group (has many markers with custom DivIcon)
                                waypointBtnLayer = layer;
                                console.log('Found waypoint layer by markers at layer', layerNum, 'with', Object.keys(layer._layers).length, 'waypoints');
                            }}
                        }}
                    }});

                    if (waypointBtnLayer) {{
                        // Remove it initially (starts hidden)
                        waypointBtnMapInstance.removeLayer(waypointBtnLayer);
                        console.log('Waypoint layer removed, ready to toggle');
                        }} else {{
                            console.error('Waypoint layer not found after checking', layerNum, 'layers');
                        }}

                    // Mark waypoint toggle as initialized
                    initComponents.waypointToggle = true;
                    checkAllInitialized();
                    }});
            }}, 100);

            function toggleWaypointButton() {{
                console.log('Waypoint button clicked');

                if (!waypointBtnMapInstance || !waypointBtnLayer) {{
                    console.error('Map or waypoint layer not ready yet');
                    return;
                }}

                var btn = document.getElementById('waypointToggleBtn');
                waypointBtnVisible = !waypointBtnVisible;

                if (waypointBtnVisible) {{
                    waypointBtnMapInstance.addLayer(waypointBtnLayer);
                    btn.classList.add('active');
                    console.log('Waypoints turned ON');
                }} else {{
                    waypointBtnMapInstance.removeLayer(waypointBtnLayer);
                    btn.classList.remove('active');
                    console.log('Waypoints turned OFF');
                }}
            }}


            // Tasks toggle implementation
            var tasksBtnMapInstance = null;
            var tasksBtnLayer = null;
            var tasksBtnVisible = false; // Start hidden

            // Initialize tasks toggle - wait for map to be ready
            setTimeout(function() {{
                function waitForTasksMap(callback, attempt) {{
                    attempt = attempt || 0;
                    var foundMap = null;
                    for (var key in window) {{
                        try {{
                            if (window[key] && typeof window[key] === 'object' && typeof window[key].eachLayer === 'function') {{
                                foundMap = window[key];
                                break;
                            }}
                        }} catch(e) {{ }}
                    }}
                    if (foundMap) {{
                        callback(foundMap);
                    }} else if (attempt < 20) {{
                        setTimeout(function() {{ waitForTasksMap(callback, attempt + 1); }}, 500);
                    }}
                }}

                waitForTasksMap(function(mapInstance) {{
                    tasksBtnMapInstance = mapInstance;
                    console.log('Tasks - Map instance found');

                    var layerNum = 0;
                    // Find the Declared Tasks FeatureGroup
                    tasksBtnMapInstance.eachLayer(function(layer) {{
                        layerNum++;

                        // Method 1: Check by name
                        if (layer.options && layer.options.name === 'Declared Tasks') {{
                            tasksBtnLayer = layer;
                            console.log('Found Declared Tasks layer by name at layer', layerNum);
                        }}

                        // Method 2: Fallback - look for FeatureGroup with polylines and markers (task lines + turnpoint markers)
                        if (!tasksBtnLayer && layer._layers && !layer._url) {{
                            var childCount = Object.keys(layer._layers).length;
                            if (childCount > 0 && childCount < 100) {{  // Tasks layer should have fewer items than waypoints/flights
                                var hasPolylines = false;
                                var hasCustomMarkers = false;

                                for (var childId in layer._layers) {{
                                    var child = layer._layers[childId];
                                    // Check for polylines (task lines)
                                    if (child._latlngs && child._latlngs.length > 0) {{
                                        hasPolylines = true;
                                    }}
                                    // Check for DivIcon markers (turnpoints with S/F markers)
                                    if (child.options && child.options.icon && child.options.icon.options &&
                                        child.options.icon.options.html &&
                                        (child.options.icon.options.html.includes('>S<') || child.options.icon.options.html.includes('>F<'))) {{
                                        hasCustomMarkers = true;
                                    }}
                                }}

                                // Tasks layer has polylines AND custom S/F markers
                                if (hasPolylines && hasCustomMarkers) {{
                                    tasksBtnLayer = layer;
                                    console.log('Found Declared Tasks layer by pattern at layer', layerNum, 'with', childCount, 'items');
                                }}
                            }}
                        }}
                    }});

                    if (tasksBtnLayer) {{
                        // Remove it initially (starts hidden)
                        tasksBtnMapInstance.removeLayer(tasksBtnLayer);
                        console.log('Tasks layer removed, ready to toggle');
                    }} else {{
                        console.log('Tasks layer not found - no tasks to display or layer not created yet');
                        // Hide the button if no tasks layer exists
                        var btn = document.getElementById('tasksToggleBtn');
                        if (btn) {{
                            btn.style.display = 'none';
                        }}
                    }}

                    // Mark tasks toggle as initialized
                    initComponents.tasksToggle = true;
                    checkAllInitialized();
                }});
            }}, 100);

            function toggleTasksButton() {{
                console.log('Tasks button clicked');

                if (!tasksBtnMapInstance || !tasksBtnLayer) {{
                    console.error('Map or tasks layer not ready yet');
                    return;
                }}

                var btn = document.getElementById('tasksToggleBtn');
                tasksBtnVisible = !tasksBtnVisible;

                if (tasksBtnVisible) {{
                    tasksBtnMapInstance.addLayer(tasksBtnLayer);
                    btn.classList.add('active');
                    console.log('Tasks turned ON');
                }} else {{
                    tasksBtnMapInstance.removeLayer(tasksBtnLayer);
                    btn.classList.remove('active');
                    console.log('Tasks turned OFF');
                }}
            }}


            // Flight tracks toggle implementation (FeatureGroup-based)
            var flightTracksBtnMapInstance = null;
            var flightTracksBtnLayer = null;
            var flightTracksBtnVisible = false; // Start hidden

            // Initialize flight tracks toggle - wait for map to be ready
            setTimeout(function() {{
                function waitForFlightTracksMap(callback, attempt) {{
                    attempt = attempt || 0;
                    var foundMap = null;
                    for (var key in window) {{
                        try {{
                            if (window[key] && typeof window[key] === 'object' && typeof window[key].eachLayer === 'function') {{
                                foundMap = window[key];
                                break;
                            }}
                        }} catch(e) {{ }}
                    }}
                    if (foundMap) {{
                        callback(foundMap);
                    }} else if (attempt < 20) {{
                        setTimeout(function() {{ waitForFlightTracksMap(callback, attempt + 1); }}, 500);
                    }}
                }}

                waitForFlightTracksMap(function(mapInstance) {{
                    flightTracksBtnMapInstance = mapInstance;
                    console.log('Flight Tracks - Map instance found');

                    // Find the Individual Flights FeatureGroup (has many polylines AND markers)
                    flightTracksBtnMapInstance.eachLayer(function(layer) {{
                        if (layer._layers && !layer._url) {{
                            var childCount = Object.keys(layer._layers).length;

                            // Check if children include both polylines and markers
                            var hasPolylines = false;
                            var hasMarkers = false;

                            for (var childId in layer._layers) {{
                                var child = layer._layers[childId];
                                if (child._latlngs && child._latlngs.length > 0) {{
                                    hasPolylines = true;
                                }}
                                if (child._radius !== undefined || child._icon) {{
                                    hasMarkers = true;
                                }}
                            }}

                            // Individual Flights has both polylines and circle markers
                            // Routes has only polylines, Waypoints has only markers
                            if (hasPolylines && hasMarkers) {{
                                flightTracksBtnLayer = layer;
                                console.log('Found Individual Flights layer with', childCount, 'items');
                            }}
                        }}
                    }});

                    if (flightTracksBtnLayer) {{
                        // Hide it initially
                        flightTracksBtnMapInstance.removeLayer(flightTracksBtnLayer);
                        console.log('Flight tracks layer found, starting hidden');

                        // Hide filter panel initially
                        var filterPanel = document.querySelector('.filter-panel');
                        if (filterPanel) {{
                            filterPanel.style.display = 'none';
                        }}
                    }} else {{
                        console.error('Individual Flights layer not found');
                    }}

                    // Mark as initialized
                    initComponents.flightTracksToggle = true;
                    checkAllInitialized();
                }});
            }}, 100);

            function toggleFlightTracksButton() {{
                console.log('Flight tracks button clicked');

                if (!flightTracksBtnMapInstance || !flightTracksBtnLayer) {{
                    console.error('Map or flight tracks layer not ready yet');
                    return;
                }}

                var btn = document.getElementById('flightTracksToggleBtn');
                var filterPanel = document.querySelector('.filter-panel');

                flightTracksBtnVisible = !flightTracksBtnVisible;

                if (flightTracksBtnVisible) {{
                    flightTracksBtnMapInstance.addLayer(flightTracksBtnLayer);
                    btn.classList.add('active');

                    // Show filter panel
                    if (filterPanel) {{
                        filterPanel.style.display = 'block';
                    }}

                    console.log('Flight tracks turned ON');
                }} else {{
                    flightTracksBtnMapInstance.removeLayer(flightTracksBtnLayer);
                    btn.classList.remove('active');

                    // Hide filter panel
                    if (filterPanel) {{
                        filterPanel.style.display = 'none';
                    }}

                    console.log('Flight tracks turned OFF');
                }}
            }}

            // Toggle flights for a specific route
            var routeFlightsVisible = {{}};  // Track visibility state for each route
            var activeRouteFlights = null;   // Currently visible route's flight indices

            function toggleRouteFlights(routeIdx, trackIndices) {{
                console.log('Toggle route', routeIdx, 'flights:', trackIndices);

                if (!flightTracksBtnMapInstance || !flightTracksBtnLayer) {{
                    console.error('Map or flight tracks layer not ready yet');
                    return;
                }}

                // Initialize visibility state for this route if not exists
                if (routeFlightsVisible[routeIdx] === undefined) {{
                    routeFlightsVisible[routeIdx] = false;
                }}

                // Toggle state
                routeFlightsVisible[routeIdx] = !routeFlightsVisible[routeIdx];
                var isVisible = routeFlightsVisible[routeIdx];

                // Update button text
                var buttonText = document.getElementById('route-toggle-text-' + routeIdx);
                if (buttonText) {{
                    buttonText.textContent = isVisible ? 'Hide Flights' : 'Show Flights';
                }}

                // Update which flights should be visible
                if (isVisible) {{
                    activeRouteFlights = trackIndices;
                    // Make sure flights layer is on
                    if (!flightTracksBtnVisible) {{
                        toggleFlightTracksButton();
                    }}
                }} else {{
                    activeRouteFlights = null;
                }}

                // Update all flight layers
                var shownCount = 0;
                var hiddenCount = 0;

                flightTracksBtnLayer.eachLayer(function(layer) {{
                    // Check if this is a polyline (flight track, not marker)
                    if (layer instanceof L.Polyline && layer.options && layer.options.flightIdx !== undefined) {{
                        var flightIdx = layer.options.flightIdx;

                        if (activeRouteFlights === null) {{
                            // No route selected - show all flights with normal style
                            flightTracksBtnMapInstance.addLayer(layer);
                            layer.setStyle({{ opacity: 0.7, weight: 2 }});
                            shownCount++;
                        }} else if (activeRouteFlights.includes(flightIdx)) {{
                            // This flight is part of the active route - highlight it
                            flightTracksBtnMapInstance.addLayer(layer);
                            layer.setStyle({{ opacity: 0.9, weight: 4 }});
                            shownCount++;
                        }} else {{
                            // This flight is not part of the active route - hide it
                            flightTracksBtnMapInstance.removeLayer(layer);
                            hiddenCount++;
                        }}
                    }}
                }});

                console.log('Route', routeIdx, ':', shownCount, 'flights shown,', hiddenCount, 'hidden');
            }}
        </script>
        '''
        flight_map.get_root().html.add_child(folium.Element(title_html))

        # Create custom filter panel with dropdowns (Excel-style)
        self._add_custom_filters(flight_map, tracks_by_year, tracks_by_pilot_display, pilot_display_to_raw, track_metadata)

        # Add custom layer selector (Google Maps style) - includes heatmap toggle
        self._add_custom_layer_selector(flight_map)

        # Add fullscreen button
        plugins.Fullscreen().add_to(flight_map)

        # Add measure control
        plugins.MeasureControl().add_to(flight_map)

        # Auto-generate satellite tiles for dates that don't have them yet
        if not skip_satellite_tiles:
            self._auto_generate_satellite_tiles(tracks, airport_code)
        else:
            logger.info("Skipping satellite tile generation (--skip-satellite-tiles flag set)")

        # Export flight data to separate JSON files before saving map
        if output_file is None:
            output_file = self.output_dir / "index.html"
        else:
            output_file = Path(output_file)

        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Export flights to external files (not embedded in HTML)
        manifest_path, flight_metadata_list = self.export_flight_data(
            tracks=tracks,
            output_dir=output_file.parent,
            deployment_mode=deployment_mode
        )

        flight_map.save(str(output_file))

        # Post-process HTML to replace VFR tile URL placeholder based on deployment mode
        with open(output_file, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Extract unique flight dates and find best default for satellite tiles
        unique_dates = sorted(set(track.flight_date for track in tracks if track.flight_date and track.flight_date != 'unknown'))
        default_satellite_date = unique_dates[-1] if unique_dates else '2024-01-01'

        logger.info(f"Found {len(unique_dates)} unique flight dates, using {default_satellite_date} as default for satellite tiles")

        if deployment_mode in ['static', 'github-pages']:
            # Use relative path for R2/CDN deployment
            vfr_tile_url = 'vfr_tiles/tiles/{z}/{x}/{y}.png'
            satellite_tile_url = f'daily_sat_tiles/{default_satellite_date}/{{z}}/{{x}}/{{y}}.jpg'
        else:
            # Use relative path for local development
            # To test locally, run a web server in the project root:
            #   cd /Users/thomasvdv/GitHub/olc-weglide && python3 -m http.server 8000
            # Then open: http://localhost:8000/downloads/STERL1_map.html
            vfr_tile_url = '../vfr_tiles/tiles/{z}/{x}/{y}.png'
            satellite_tile_url = f'../daily_sat_tiles/{default_satellite_date}/{{z}}/{{x}}/{{y}}.jpg'

        html_content = html_content.replace('{VFR_TILE_URL}', vfr_tile_url)
        html_content = html_content.replace('{SATELLITE_TILE_URL}', satellite_tile_url)

        # Inject available satellite dates into JavaScript for better UX
        dates_js = f'var availableSatelliteDates = {json.dumps(unique_dates)};'
        html_content = html_content.replace('var currentSatelliteDate = null;',
                                           f'{dates_js}\n            var currentSatelliteDate = "{default_satellite_date}";')

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"Map saved to {output_file} (deployment mode: {deployment_mode})")
        return output_file

    def generate_airport_map(
        self,
        airport_code: str,
        max_tracks: Optional[int] = None,
        min_points: Optional[float] = None,
        deployment_mode: str = 'local',
        skip_satellite_tiles: bool = False,
    ) -> Path:
        """
        Generate a map for all flights from a specific airport

        Args:
            airport_code: Airport code (e.g., 'STERL1')
            max_tracks: Maximum number of tracks to display (default: all)
            min_points: Minimum points score to include flights (default: all)
            deployment_mode: Deployment mode - 'local' or 'static' (for R2/CDN)
            skip_satellite_tiles: Skip automatic satellite tile generation

        Returns:
            Path to generated HTML file
        """
        # Find airport directory
        airport_dir = self.output_dir / airport_code

        if not airport_dir.exists():
            raise ValueError(f"Airport directory not found: {airport_dir}")

        # Find all IGC files
        igc_files = list(airport_dir.rglob('*.igc'))

        if not igc_files:
            raise ValueError(f"No IGC files found in {airport_dir}")

        logger.info(f"Found {len(igc_files)} IGC files for {airport_code}")

        # Load metadata for all years
        from .metadata import MetadataStore
        metadata_store = MetadataStore(self.output_dir)
        all_metadata = {}

        # Find all years with metadata
        for year_dir in airport_dir.iterdir():
            if year_dir.is_dir() and year_dir.name.isdigit():
                year_metadata = metadata_store.load_metadata(airport_code, year_dir.name)
                all_metadata.update(year_metadata)

        logger.info(f"Loaded metadata for {len(all_metadata)} flights")

        # Create a secondary index for matching by pilot + date
        # (since filenames may not match due to flight_id vs dsid discrepancy)
        def normalize_pilot_name(pilot: str) -> str:
            """Normalize pilot name to match filename format"""
            safe = pilot.replace(' ', '_').replace('/', '-').replace('\\', '-')
            safe = ''.join(c for c in safe if c.isalnum() or c in ('_', '-', '(', ')'))
            return safe

        pilot_date_index = {}
        pilot_only_index = {}  # Fallback index for when dates don't match
        for dsid, metadata in all_metadata.items():
            safe_pilot = normalize_pilot_name(metadata.pilot)

            # Primary index: pilot + date (when date is available)
            if metadata.date:
                key = (safe_pilot, metadata.date)
                pilot_date_index[key] = metadata

            # Fallback index: just pilot name (for when dates are empty or don't match)
            # Store as list to handle multiple flights from same pilot
            if safe_pilot not in pilot_only_index:
                pilot_only_index[safe_pilot] = []
            pilot_only_index[safe_pilot].append(metadata)

        # Parse all IGC files
        tracks = []
        failed_count = 0
        enriched_count = 0
        for igc_file in igc_files:
            track = self.parse_igc_file(igc_file)
            if track:
                # Try to enrich track with metadata
                # Strategy 1: Try matching by pilot name + date (most reliable)
                metadata = None
                key = (track.pilot_name, track.flight_date)
                if key in pilot_date_index:
                    metadata = pilot_date_index[key]

                # Strategy 2: Fallback to pilot-only matching if no date match
                # (metadata may have empty dates)
                if not metadata and track.pilot_name in pilot_only_index:
                    candidates = pilot_only_index[track.pilot_name]
                    if len(candidates) == 1:
                        # Single flight from this pilot - safe to match
                        metadata = candidates[0]
                    else:
                        # Multiple flights from same pilot - try to match by date
                        for candidate in candidates:
                            # Since metadata dates are often empty, we'll take the first one
                            # that matches our flight date if available
                            if candidate.date and candidate.date == track.flight_date:
                                metadata = candidate
                                break

                        # If still no match, we can't reliably determine which flight this is
                        # Log a debug message but don't apply metadata
                        if not metadata:
                            logger.debug(f"Could not match flight {track.filename} to metadata - "
                                       f"multiple flights from {track.pilot_name}, dates don't match")

                # Apply metadata if we found a match
                if metadata:
                    track.points = metadata.points
                    track.flight_id = metadata.flight_id
                    track.dsid = metadata.dsid
                    # Use distance and speed from OLC metadata if available
                    if metadata.distance:
                        track.distance_km = metadata.distance
                    if metadata.speed:
                        track.avg_speed_kmh = metadata.speed
                    # Use aircraft from OLC metadata if available
                    if metadata.aircraft:
                        track.aircraft = metadata.aircraft
                    enriched_count += 1

                tracks.append(track)
            else:
                failed_count += 1

        if not tracks:
            raise ValueError(
                f"Failed to parse any valid IGC files from {airport_dir}. "
                f"{failed_count} files appear to be HTML error pages. "
                f"You may need to re-download these flights."
            )

        logger.info(f"Successfully parsed {len(tracks)} valid tracks")
        logger.info(f"Enriched {enriched_count}/{len(tracks)} tracks with OLC metadata (distance, speed, aircraft)")
        if failed_count > 0:
            logger.warning(
                f"Skipped {failed_count} invalid files (likely HTML error pages). "
                f"Re-download with: olc-download download --airport-code {airport_code} --all-pilots --force"
            )

        # Limit number of tracks if specified
        if max_tracks and len(tracks) > max_tracks:
            logger.info(f"Limiting to {max_tracks} tracks (out of {len(tracks)})")
            # Randomly sample tracks to get a good distribution
            random.shuffle(tracks)
            tracks = tracks[:max_tracks]

        # Create the map
        return self.create_map(
            airport_code,
            tracks,
            deployment_mode=deployment_mode,
            skip_satellite_tiles=skip_satellite_tiles
        )
