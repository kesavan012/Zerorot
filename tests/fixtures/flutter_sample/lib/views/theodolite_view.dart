/// TheodoliteView — Digital theodolite display with horizontal/vertical
/// angle readout, EDM distance measurement, and bubble leveling indicator.

import 'package:flutter/material.dart';

class TheodoliteView extends StatefulWidget {
  const TheodoliteView({super.key});
  @override
  State<TheodoliteView> createState() => _TheodoliteViewState();
}

class _TheodoliteViewState extends State<TheodoliteView> {
  double horizontalAngle = 0.0;
  double verticalAngle = 90.0;
  double slopeDistance = 0.0;

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Text('HA: ${horizontalAngle.toStringAsFixed(4)}°'),
      Text('VA: ${verticalAngle.toStringAsFixed(4)}°'),
      Text('SD: ${slopeDistance.toStringAsFixed(3)} m'),
    ]);
  }
}
