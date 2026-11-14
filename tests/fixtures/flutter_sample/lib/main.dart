/// GeoSight — Total Station Companion App
/// 
/// Entry point for the Flutter application. Initialises sensor services,
/// database helpers, and routes to the main navigation screen.
/// Supports physical sensor calibration, theodolite angle measurement,
/// stakeout mode, traverse survey computation, and CSV/DXF export.

import 'package:flutter/material.dart';
import 'services/sensor_service.dart';
import 'database/db_helper.dart';
import 'views/home_view.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await DbHelper.instance.init();
  await SensorService.instance.start();
  runApp(const GeoSightApp());
}

class GeoSightApp extends StatelessWidget {
  const GeoSightApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GeoSight',
      theme: ThemeData(
        colorSchemeSeed: Colors.indigo,
        useMaterial3: true,
      ),
      home: const HomeView(),
    );
  }
}
