# ÖBB rail (HAFAS EVA)
WIEN_HERNALS_EVA       = '1191701'
WIEN_HEILIGENSTADT_EVA = '1191901'
KREMS_EVA              = '1130101'

# Nextbike
NEXTBIKE_SYSTEM_BASE   = 'https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_la/en'
KREMS_BAHNHOF_BIKE_ID  = '42835'   # virtual station, geofenced
KREMS_CAMPUS_BIKE_ID   = '42845'   # physical station

# Coordinates
HOME_VIENNA_LAT,   HOME_VIENNA_LON   = 48.2242, 16.3202
KREMS_BAHNHOF_LAT, KREMS_BAHNHOF_LON = 48.4094, 15.6045
KREMS_CAMPUS_LAT,  KREMS_CAMPUS_LON  = 48.4078, 15.5900

# Walking constants (seconds)
WALK_HOME_TO_HERNALS_S   = 7 * 60 + 70
WALK_CAMPUS_TO_BAHNHOF_S = 19 * 60
WALK_CAMPUS_TO_KLPU_S    = 8 * 60   # estimate

# Kremser Stadtbus - Line 1 stop (for return leg: Campus → Bahnhof)
BUS1_KLPU_EVA = '391060'
BUS1_HEADWAY_MIN = 30
BUS1_FIRST_DEPARTURE_HHMM = (5, 7)   # 05:07 from Stein-Mautern (first bus touches KLPU ~05:10)
BUS1_LAST_DEPARTURE_HHMM  = (19, 17) # 19:17 from Stein-Mautern (last bus touches KLPU ~19:20)

# Leg durations (seconds) - derived metrics reference these
RIDE_S45_HERNALS_TO_HEILIGENSTADT_S = 12 * 60
TRANSFER_HEILIGENSTADT_S45_TO_REX_S = 2 * 60
RIDE_REX4_HEILIGENSTADT_TO_KREMS_S  = 60 * 60

# Return leg: campus → Krems Bahnhof
WALK_CAMPUS_TO_BAHNHOF_S = 19 * 60        # already exists
WALK_CAMPUS_TO_KLPU_S    = 8 * 60         # already exists
BIKE_CAMPUS_TO_BAHNHOF_S = 8 * 60         # walk-to-station + unlock + ride, total
BUS_KLPU_TO_BAHNHOF_S    = 7 * 60         # KLPU → Krems Bahnhof scheduled ride time

# InfluxDB
INFLUX_URL    = "http://localhost:8086"
INFLUX_ORG    = "your-org-name"
INFLUX_TOKEN  = "your-write-token"
INFLUX_BUCKET = "commute"