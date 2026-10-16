import 'dart:math';
import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../models/plot.dart';

class InteractiveCadastralMap extends StatefulWidget {
  final List<Plot> plots;
  final Plot? selectedPlot;
  final Function(Plot) onPlotSelected;

  const InteractiveCadastralMap({
    super.key,
    required this.plots,
    required this.selectedPlot,
    required this.onPlotSelected,
  });

  @override
  State<InteractiveCadastralMap> createState() => _InteractiveCadastralMapState();
}

class _InteractiveCadastralMapState extends State<InteractiveCadastralMap> {
  // Almaty bounding box
  final double minLat = 43.14;
  final double maxLat = 43.36;
  final double minLng = 76.78;
  final double maxLng = 77.15;

  double zoom = 1.0;
  Offset panOffset = Offset.zero;
  Offset? _startFocalPoint;
  double _startZoom = 1.0;
  Offset _startPan = Offset.zero;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(24),
      child: Stack(
        children: [
          // Interactive Gesture Area
          GestureDetector(
            onScaleStart: (details) {
              _startFocalPoint = details.focalPoint;
              _startZoom = zoom;
              _startPan = panOffset;
            },
            onScaleUpdate: (details) {
              setState(() {
                zoom = (_startZoom * details.scale).clamp(0.8, 3.5);
                if (_startFocalPoint != null) {
                  panOffset = _startPan + (details.focalPoint - _startFocalPoint!);
                }
              });
            },
            onTapUp: (details) {
              _handleTap(details.localPosition, context.size ?? const Size(400, 300));
            },
            child: CustomPaint(
              size: Size.infinite,
              painter: _MapCanvasPainter(
                plots: widget.plots,
                selectedPlot: widget.selectedPlot,
                minLat: minLat,
                maxLat: maxLat,
                minLng: minLng,
                maxLng: maxLng,
                zoom: zoom,
                pan: panOffset,
              ),
            ),
          ),

          // Zoom Buttons Overlay
          Positioned(
            right: 14,
            bottom: 14,
            child: Column(
              children: [
                _buildMapControl(
                  icon: Icons.add,
                  onPressed: () {
                    setState(() {
                      zoom = (zoom * 1.25).clamp(0.8, 3.5);
                    });
                  },
                ),
                const SizedBox(height: 8),
                _buildMapControl(
                  icon: Icons.remove,
                  onPressed: () {
                    setState(() {
                      zoom = (zoom / 1.25).clamp(0.8, 3.5);
                    });
                  },
                ),
                const SizedBox(height: 8),
                _buildMapControl(
                  icon: Icons.my_location,
                  onPressed: () {
                    setState(() {
                      zoom = 1.0;
                      panOffset = Offset.zero;
                    });
                  },
                ),
              ],
            ),
          ),

          // Map Legend Overlay (Top Left)
          Positioned(
            left: 14,
            top: 14,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xE6FFFFFF),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0x332F5B8A), width: 1),
                boxShadow: const [
                  BoxShadow(color: Color(0x10000000), blurRadius: 10),
                ],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    decoration: const BoxDecoration(
                      color: AnyqColors.clarity,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 5),
                  const Text(
                    'Кадастровый слой Алматы',
                    style: TextStyle(
                      color: AnyqColors.primary,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMapControl({required IconData icon, required VoidCallback onPressed}) {
    return Container(
      width: 36,
      height: 36,
      decoration: BoxDecoration(
        color: Colors.white,
        shape: BoxShape.circle,
        border: Border.all(color: const Color(0x33CBD5E1), width: 1),
        boxShadow: const [
          BoxShadow(color: Color(0x15000000), blurRadius: 8, offset: Offset(0, 2)),
        ],
      ),
      child: IconButton(
        icon: Icon(icon, size: 18, color: AnyqColors.primary),
        padding: EdgeInsets.zero,
        onPressed: onPressed,
      ),
    );
  }

  void _handleTap(Offset localPos, Size size) {
    for (final plot in widget.plots) {
      if (plot.polygon.isEmpty) continue;
      // Get centroid of plot
      double avgLat = plot.polygon.map((p) => p.lat).reduce((a, b) => a + b) / plot.polygon.length;
      double avgLng = plot.polygon.map((p) => p.lng).reduce((a, b) => a + b) / plot.polygon.length;

      final plotScreenPoint = _latLngToScreen(avgLat, avgLng, size);
      if ((plotScreenPoint - localPos).distance < 36 * zoom) {
        widget.onPlotSelected(plot);
        break;
      }
    }
  }

  Offset _latLngToScreen(double lat, double lng, Size size) {
    double normX = (lng - minLng) / (maxLng - minLng);
    double normY = 1.0 - ((lat - minLat) / (maxLat - minLat));

    double cx = size.width / 2;
    double cy = size.height / 2;

    double x = cx + ((normX * size.width) - cx + panOffset.dx) * zoom;
    double y = cy + ((normY * size.height) - cy + panOffset.dy) * zoom;

    return Offset(x, y);
  }
}

class _MapCanvasPainter extends CustomPainter {
  final List<Plot> plots;
  final Plot? selectedPlot;
  final double minLat;
  final double maxLat;
  final double minLng;
  final double maxLng;
  final double zoom;
  final Offset pan;

  _MapCanvasPainter({
    required this.plots,
    required this.selectedPlot,
    required this.minLat,
    required this.maxLat,
    required this.minLng,
    required this.maxLng,
    required this.zoom,
    required this.pan,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // 1. Warm Terrain background
    final bgPaint = Paint()..color = const Color(0xFFEBE3D5);
    canvas.drawRect(Rect.fromLTWH(0, 0, size.width, size.height), bgPaint);

    // 2. Mountain silhouette in South (Medeu / Kok-Tobe)
    final mountainPaint = Paint()
      ..color = const Color(0xFFD6C8B4)
      ..style = PaintingStyle.fill;

    final mountainPath = Path();
    mountainPath.moveTo(0, size.height);
    mountainPath.lineTo(0, size.height * 0.72);
    mountainPath.quadraticBezierTo(size.width * 0.25, size.height * 0.65, size.width * 0.5, size.height * 0.78);
    mountainPath.quadraticBezierTo(size.width * 0.75, size.height * 0.58, size.width, size.height * 0.70);
    mountainPath.lineTo(size.width, size.height);
    mountainPath.close();
    canvas.drawPath(mountainPath, mountainPaint);

    // 3. Cadastral Grid lines
    final gridPaint = Paint()
      ..color = const Color(0x180F2942)
      ..strokeWidth = 1.0;

    for (double i = 0; i < size.width; i += 40 * zoom) {
      canvas.drawLine(Offset(i, 0), Offset(i, size.height), gridPaint);
    }
    for (double i = 0; i < size.height; i += 40 * zoom) {
      canvas.drawLine(Offset(0, i), Offset(size.width, i), gridPaint);
    }

    // 4. Roads (Al-Farabi, Dostyk, Talgar)
    final roadPaint = Paint()
      ..color = const Color(0xFFFCFBF9)
      ..strokeWidth = 3.5 * zoom
      ..style = PaintingStyle.stroke;

    final roadBorder = Paint()
      ..color = const Color(0x300F2942)
      ..strokeWidth = 5.0 * zoom
      ..style = PaintingStyle.stroke;

    final alFarabiPath = Path();
    alFarabiPath.moveTo(0, size.height * 0.62);
    alFarabiPath.cubicTo(
      size.width * 0.35, size.height * 0.58,
      size.width * 0.65, size.height * 0.60,
      size.width, size.height * 0.50,
    );
    canvas.drawPath(alFarabiPath, roadBorder);
    canvas.drawPath(alFarabiPath, roadPaint);

    final dostykPath = Path();
    dostykPath.moveTo(size.width * 0.55, 0);
    dostykPath.lineTo(size.width * 0.52, size.height);
    canvas.drawPath(dostykPath, roadBorder);
    canvas.drawPath(dostykPath, roadPaint);

    // 5. Draw Plot Polygons and Pins
    for (final plot in plots) {
      if (plot.polygon.isEmpty) continue;

      final isSelected = selectedPlot?.id == plot.id;
      final polyPath = Path();

      for (int i = 0; i < plot.polygon.length; i++) {
        final pt = plot.polygon[i];
        final screenPt = _toScreen(pt.lat, pt.lng, size);
        if (i == 0) {
          polyPath.moveTo(screenPt.dx, screenPt.dy);
        } else {
          polyPath.lineTo(screenPt.dx, screenPt.dy);
        }
      }
      polyPath.close();

      // Polygon Fill
      Color fillColor;
      if (plot.verified && !plot.hasRestrictions) {
        fillColor = const Color(0x40059669); // clarity emerald
      } else if (plot.hasRestrictions) {
        fillColor = const Color(0x40B45309); // caution amber
      } else {
        fillColor = const Color(0x3094A3B8);
      }

      if (isSelected) {
        fillColor = const Color(0x80D4AF37); // golden active fill
      }

      final fillPaint = Paint()..color = fillColor..style = PaintingStyle.fill;
      canvas.drawPath(polyPath, fillPaint);

      // Cadastral blue boundary line #2F5B8A
      final strokePaint = Paint()
        ..color = isSelected ? AnyqColors.gold : const Color(0xFF2F5B8A)
        ..strokeWidth = isSelected ? 3.0 : 1.8
        ..style = PaintingStyle.stroke;
      canvas.drawPath(polyPath, strokePaint);

      // Draw Marker Pin at centroid
      double avgLat = plot.polygon.map((p) => p.lat).reduce((a, b) => a + b) / plot.polygon.length;
      double avgLng = plot.polygon.map((p) => p.lng).reduce((a, b) => a + b) / plot.polygon.length;
      final centroid = _toScreen(avgLat, avgLng, size);

      _drawPlotPin(canvas, centroid, plot, isSelected);
    }
  }

  void _drawPlotPin(Canvas canvas, Offset pos, Plot plot, bool isSelected) {
    // Pulse circle if selected
    if (isSelected) {
      final pulsePaint = Paint()
        ..color = const Color(0x33D4AF37)
        ..style = PaintingStyle.fill;
      canvas.drawCircle(pos, 22 * zoom, pulsePaint);
    }

    // Pin base
    final pinPaint = Paint()
      ..color = isSelected ? AnyqColors.primary : Colors.white
      ..style = PaintingStyle.fill;

    final shadowPaint = Paint()
      ..color = const Color(0x28000000)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);

    canvas.drawCircle(pos.translate(0, 2), 12 * zoom, shadowPaint);
    canvas.drawCircle(pos, 12 * zoom, pinPaint);

    final borderPaint = Paint()
      ..color = plot.verified ? AnyqColors.clarity : AnyqColors.caution
      ..strokeWidth = 2.5
      ..style = PaintingStyle.stroke;
    canvas.drawCircle(pos, 12 * zoom, borderPaint);

    // Center dot
    final dotPaint = Paint()
      ..color = plot.verified ? AnyqColors.clarity : AnyqColors.caution
      ..style = PaintingStyle.fill;
    canvas.drawCircle(pos, 4 * zoom, dotPaint);
  }

  Offset _toScreen(double lat, double lng, Size size) {
    double normX = (lng - minLng) / (maxLng - minLng);
    double normY = 1.0 - ((lat - minLat) / (maxLat - minLat));

    double cx = size.width / 2;
    double cy = size.height / 2;

    double x = cx + ((normX * size.width) - cx + pan.dx) * zoom;
    double y = cy + ((normY * size.height) - cy + pan.dy) * zoom;

    return Offset(x, y);
  }

  @override
  bool shouldRepaint(covariant _MapCanvasPainter oldDelegate) {
    return oldDelegate.zoom != zoom ||
        oldDelegate.pan != pan ||
        oldDelegate.selectedPlot?.id != selectedPlot?.id ||
        oldDelegate.plots.length != plots.length;
  }
}
