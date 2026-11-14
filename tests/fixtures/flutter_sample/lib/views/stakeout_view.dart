/// StakeoutView — On-site stakeout navigation view.
/// Guides the user to a target coordinate using compass bearing,
/// distance-to-go, and AR camera overlay.

import 'package:flutter/material.dart';

class StakeoutView extends StatefulWidget {
  const StakeoutView({super.key});
  @override
  State<StakeoutView> createState() => _StakeoutViewState();
}

class _StakeoutViewState extends State<StakeoutView> {
  double targetNorthing = 0.0;
  double targetEasting  = 0.0;
  double distanceToGo   = 0.0;
  double bearingToTarget = 0.0;

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Text('Distance to go: ${distanceToGo.toStringAsFixed(3)} m'),
      Text('Bearing: ${bearingToTarget.toStringAsFixed(2)}°'),
    ]);
  }
}
