/// DbHelper — SQLite local database for offline survey data persistence.
///
/// Stores survey sessions, theodolite readings, stakeout points,
/// traverse computations, and calibration profiles.

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';

class DbHelper {
  static final DbHelper instance = DbHelper._();
  DbHelper._();

  Database? _db;

  Future<void> init() async {
    final path = join(await getDatabasesPath(), 'geosight.db');
    _db = await openDatabase(path, version: 1, onCreate: _onCreate);
  }

  Future<void> _onCreate(Database db, int version) async {
    await db.execute('''
      CREATE TABLE survey_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, created_at TEXT, project_id INTEGER
      )
    ''');
    await db.execute('''
      CREATE TABLE theodolite_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER, horizontal_angle REAL,
        vertical_angle REAL, slope_distance REAL, timestamp TEXT
      )
    ''');
    await db.execute('''
      CREATE TABLE stakeout_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER, northing REAL, easting REAL,
        elevation REAL, label TEXT
      )
    ''');
    await db.execute('''
      CREATE TABLE traverse_stations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER, station_name TEXT,
        bearing REAL, distance REAL, coordinate_x REAL, coordinate_y REAL
      )
    ''');
  }

  Future<List<Map>> getSurveySessions() async =>
      await _db!.query('survey_sessions', orderBy: 'created_at DESC');

  Future<int> insertReading(Map<String, dynamic> data) async =>
      await _db!.insert('theodolite_readings', data);

  Future<List<Map>> getTraverseStations(int sessionId) async =>
      await _db!.query('traverse_stations',
          where: 'session_id = ?', whereArgs: [sessionId]);
}
