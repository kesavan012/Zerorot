/// CameraOverlayView — Augmented reality camera overlay for field guidance.
/// Superimposes measurement vectors, stake directions, and prism targets
/// onto the live camera feed.

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';

class CameraOverlayView extends StatefulWidget {
  const CameraOverlayView({super.key});
  @override
  State<CameraOverlayView> createState() => _CameraOverlayViewState();
}

class _CameraOverlayViewState extends State<CameraOverlayView> {
  CameraController? _controller;

  @override
  Widget build(BuildContext context) {
    return Stack(children: [
      if (_controller != null) CameraPreview(_controller!),
      // AR overlay painter
      CustomPaint(painter: OverlayPainter()),
    ]);
  }
}

class OverlayPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {}
  @override
  bool shouldRepaint(covariant CustomPainter old) => true;
}
