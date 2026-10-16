import 'dart:math';
import 'package:flutter/material.dart';
import '../core/theme.dart';

class BimViewer3D extends StatefulWidget {
  final String projectTitle;

  const BimViewer3D({
    super.key,
    required this.projectTitle,
  });

  @override
  State<BimViewer3D> createState() => _BimViewer3DState();
}

class _BimViewer3DState extends State<BimViewer3D> with SingleTickerProviderStateMixin {
  double rotX = 0.45; // Elevation angle
  double rotY = 0.75; // Azimuth angle
  double scale = 1.0;
  double clipHeight = 9.0; // Section cut 0 to 9m

  bool showArch = true;
  bool showConcrete = true;
  bool showRoof = true;
  bool showMep = true;
  bool showRebar = false;

  String? selectedMarker = 'Колонна К-1 (400×400, класс B25)';

  Offset? _lastPanPos;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // 3D Canvas Viewport
        Container(
          height: 280,
          width: double.infinity,
          margin: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: const Color(0xFFF1F5F9),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(color: const Color(0x60CBD5E1), width: 1.2),
            boxShadow: const [
              BoxShadow(color: Color(0x0C0F172A), blurRadius: 20, offset: Offset(0, 6)),
            ],
          ),
          child: Stack(
            children: [
              // 3D Model Interactive Surface
              GestureDetector(
                onScaleStart: (details) {
                  _lastPanPos = details.localFocalPoint;
                },
                onScaleUpdate: (details) {
                  setState(() {
                    if (_lastPanPos != null) {
                      final delta = details.localFocalPoint - _lastPanPos!;
                      rotY += delta.dx * 0.012;
                      rotX = (rotX - delta.dy * 0.012).clamp(0.1, 1.2);
                    }
                    _lastPanPos = details.localFocalPoint;
                    scale = (scale * details.scale).clamp(0.7, 2.2);
                  });
                },
                child: CustomPaint(
                  size: Size.infinite,
                  painter: _BimModelPainter(
                    rotX: rotX,
                    rotY: rotY,
                    scale: scale,
                    clipHeight: clipHeight,
                    showArch: showArch,
                    showConcrete: showConcrete,
                    showRoof: showRoof,
                    showMep: showMep,
                    showRebar: showRebar,
                  ),
                ),
              ),

              // Title and Reset Button Overlay
              Positioned(
                top: 12,
                left: 14,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: const Color(0xE6FFFFFF),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: const Color(0x332F5B8A), width: 1),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.view_in_ar, size: 14, color: AnyqColors.primary),
                      const SizedBox(width: 5),
                      Text(
                        '3D BIM Model · ${scale.toStringAsFixed(1)}x',
                        style: const TextStyle(
                          color: AnyqColors.primary,
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              Positioned(
                top: 10,
                right: 12,
                child: IconButton(
                  icon: const Icon(Icons.refresh, size: 20, color: AnyqColors.primary),
                  onPressed: () {
                    setState(() {
                      rotX = 0.45;
                      rotY = 0.75;
                      scale = 1.0;
                      clipHeight = 9.0;
                    });
                  },
                ),
              ),

              // Active Inspection Marker Pill
              if (selectedMarker != null)
                Positioned(
                  bottom: 12,
                  left: 14,
                  right: 14,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
                    decoration: BoxDecoration(
                      color: const Color(0xF00F2942),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: const Color(0x40D4AF37), width: 1),
                      boxShadow: const [
                        BoxShadow(color: Color(0x20000000), blurRadius: 10),
                      ],
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.info_outline, size: 16, color: AnyqColors.gold),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            selectedMarker!,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),

        const SizedBox(height: 12),

        // Section Cut Slider
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Row(
            children: [
              const Icon(Icons.content_cut, size: 16, color: AnyqColors.inkMute),
              const SizedBox(width: 8),
              Text(
                'Сечение: ${clipHeight.toStringAsFixed(1)}м',
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AnyqColors.ink),
              ),
              Expanded(
                child: Slider(
                  value: clipHeight,
                  min: 1.0,
                  max: 9.0,
                  activeColor: AnyqColors.primary,
                  inactiveColor: const Color(0xFFCBD5E1),
                  onChanged: (val) {
                    setState(() {
                      clipHeight = val;
                    });
                  },
                ),
              ),
            ],
          ),
        ),

        // Layer Filter Chips
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              _buildLayerChip('Архитектура', showArch, (v) => setState(() => showArch = v)),
              const SizedBox(width: 6),
              _buildLayerChip('Железобетон', showConcrete, (v) => setState(() => showConcrete = v)),
              const SizedBox(width: 6),
              _buildLayerChip('Кровля', showRoof, (v) => setState(() => showRoof = v)),
              const SizedBox(width: 6),
              _buildLayerChip('Инженерия ОВ/ВК', showMep, (v) => setState(() => showMep = v)),
              const SizedBox(width: 6),
              _buildLayerChip('Арматура', showRebar, (v) => setState(() => showRebar = v)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildLayerChip(String title, bool active, Function(bool) onChanged) {
    return FilterChip(
      label: Text(title),
      selected: active,
      onSelected: onChanged,
      labelStyle: TextStyle(
        color: active ? Colors.white : AnyqColors.ink,
        fontSize: 11,
        fontWeight: FontWeight.w600,
      ),
      backgroundColor: Colors.white,
      selectedColor: AnyqColors.primary,
      checkmarkColor: AnyqColors.gold,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(
          color: active ? AnyqColors.primary : const Color(0xFFCBD5E1),
          width: 1,
        ),
      ),
    );
  }
}

class _BimModelPainter extends CustomPainter {
  final double rotX;
  final double rotY;
  final double scale;
  final double clipHeight;
  final bool showArch;
  final bool showConcrete;
  final bool showRoof;
  final bool showMep;
  final bool showRebar;

  _BimModelPainter({
    required this.rotX,
    required this.rotY,
    required this.scale,
    required this.clipHeight,
    required this.showArch,
    required this.showConcrete,
    required this.showRoof,
    required this.showMep,
    required this.showRebar,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2 + 30;

    // 1. Ground Grid
    final gridPaint = Paint()
      ..color = const Color(0x30CBD5E1)
      ..strokeWidth = 1.0;

    for (int i = -4; i <= 4; i++) {
      final p1 = _project(i * 30.0, 0, -120, cx, cy);
      final p2 = _project(i * 30.0, 0, 120, cx, cy);
      canvas.drawLine(p1, p2, gridPaint);

      final p3 = _project(-120, 0, i * 30.0, cx, cy);
      final p4 = _project(120, 0, i * 30.0, cx, cy);
      canvas.drawLine(p3, p4, gridPaint);
    }

    // 2. Foundation Slab
    if (showConcrete && clipHeight >= 1.0) {
      _drawBox(
        canvas: canvas,
        cx: cx,
        cy: cy,
        min: const _Vec3(-70, 0, -50),
        max: const _Vec3(70, 14, 50),
        fillColor: const Color(0xFF94A3B8),
        strokeColor: const Color(0xFF475569),
      );
    }

    // 3. First Floor Columns
    if (showConcrete && clipHeight >= 2.5) {
      final colColor = const Color(0xFF64748B);
      final colStroke = const Color(0xFF334155);

      final colPositions = [
        const Offset(-65, -45),
        const Offset(65, -45),
        const Offset(-65, 45),
        const Offset(65, 45),
        const Offset(0, -45),
        const Offset(0, 45),
      ];

      for (var pos in colPositions) {
        _drawBox(
          canvas: canvas,
          cx: cx,
          cy: cy,
          min: _Vec3(pos.dx - 6, 14, pos.dy - 6),
          max: _Vec3(pos.dx + 6, min(56.0, clipHeight * 10), pos.dy + 6),
          fillColor: colColor,
          strokeColor: colStroke,
        );
      }
    }

    // 4. First Floor Walls (Arch)
    if (showArch && clipHeight >= 3.0) {
      _drawBox(
        canvas: canvas,
        cx: cx,
        cy: cy,
        min: const _Vec3(-60, 14, -40),
        max: _Vec3(60, min(54.0, clipHeight * 10), 40),
        fillColor: const Color(0x60CBD5E1),
        strokeColor: const Color(0xFF0F2942),
      );
    }

    // 5. MEP Engineering Ducts (Orange / Cyan pipes)
    if (showMep && clipHeight >= 2.0) {
      final pipePaint = Paint()
        ..color = const Color(0xFFF97316)
        ..strokeWidth = 3.5 * scale
        ..style = PaintingStyle.stroke;

      final p1 = _project(-50, 48, -30, cx, cy);
      final p2 = _project(50, 48, -30, cx, cy);
      final p3 = _project(50, 48, 20, cx, cy);
      canvas.drawLine(p1, p2, pipePaint);
      canvas.drawLine(p2, p3, pipePaint);
    }

    // 6. Second Floor Slab & Walls
    if (showConcrete && clipHeight >= 6.0) {
      _drawBox(
        canvas: canvas,
        cx: cx,
        cy: cy,
        min: const _Vec3(-72, 56, -52),
        max: const _Vec3(72, 64, 52),
        fillColor: const Color(0xFF94A3B8),
        strokeColor: const Color(0xFF475569),
      );
    }

    // 7. Roof (Gable roof)
    if (showRoof && clipHeight >= 8.5) {
      final roofPaint = Paint()
        ..color = const Color(0xCC0F2942)
        ..style = PaintingStyle.fill;
      final roofStroke = Paint()
        ..color = AnyqColors.gold
        ..strokeWidth = 1.5 * scale
        ..style = PaintingStyle.stroke;

      final r1 = _project(-75, 64, -55, cx, cy);
      final r2 = _project(75, 64, -55, cx, cy);
      final r3 = _project(0, 105, -55, cx, cy);

      final r4 = _project(-75, 64, 55, cx, cy);
      final r5 = _project(75, 64, 55, cx, cy);
      final r6 = _project(0, 105, 55, cx, cy);

      final frontGable = Path()..moveTo(r1.dx, r1.dy)..lineTo(r2.dx, r2.dy)..lineTo(r3.dx, r3.dy)..close();
      canvas.drawPath(frontGable, roofPaint);
      canvas.drawPath(frontGable, roofStroke);

      final roofSlope = Path()
        ..moveTo(r1.dx, r1.dy)
        ..lineTo(r3.dx, r3.dy)
        ..lineTo(r6.dx, r6.dy)
        ..lineTo(r4.dx, r4.dy)
        ..close();
      canvas.drawPath(roofSlope, Paint()..color = const Color(0xAA1E3A8A));
      canvas.drawPath(roofSlope, roofStroke);
    }
  }

  void _drawBox({
    required Canvas canvas,
    required double cx,
    required double cy,
    required _Vec3 min,
    required _Vec3 max,
    required Color fillColor,
    required Color strokeColor,
  }) {
    final v0 = _project(min.x, min.y, min.z, cx, cy);
    final v1 = _project(max.x, min.y, min.z, cx, cy);
    final v2 = _project(max.x, max.y, min.z, cx, cy);
    final v3 = _project(min.x, max.y, min.z, cx, cy);

    final v4 = _project(min.x, min.y, max.z, cx, cy);
    final v5 = _project(max.x, min.y, max.z, cx, cy);
    final v6 = _project(max.x, max.y, max.z, cx, cy);
    final v7 = _project(min.x, max.y, max.z, cx, cy);

    final fillPaint = Paint()..color = fillColor..style = PaintingStyle.fill;
    final strokePaint = Paint()..color = strokeColor..strokeWidth = 1.0 * scale..style = PaintingStyle.stroke;

    // Front Face
    final front = Path()..moveTo(v0.dx, v0.dy)..lineTo(v1.dx, v1.dy)..lineTo(v2.dx, v2.dy)..lineTo(v3.dx, v3.dy)..close();
    canvas.drawPath(front, fillPaint);
    canvas.drawPath(front, strokePaint);

    // Top Face
    final top = Path()..moveTo(v3.dx, v3.dy)..lineTo(v2.dx, v2.dy)..lineTo(v6.dx, v6.dy)..lineTo(v7.dx, v7.dy)..close();
    canvas.drawPath(top, fillPaint);
    canvas.drawPath(top, strokePaint);

    // Right Face
    final right = Path()..moveTo(v1.dx, v1.dy)..lineTo(v5.dx, v5.dy)..lineTo(v6.dx, v6.dy)..lineTo(v2.dx, v2.dy)..close();
    canvas.drawPath(right, fillPaint);
    canvas.drawPath(right, strokePaint);
  }

  Offset _project(double x, double y, double z, double cx, double cy) {
    // 3D rotation matrix
    double cosY = cos(rotY);
    double sinY = sin(rotY);
    double cosX = cos(rotX);
    double sinX = sin(rotX);

    // Rotate around Y
    double x1 = x * cosY + z * sinY;
    double z1 = -x * sinY + z * cosY;

    // Rotate around X
    double y2 = y * cosX - z1 * sinX;

    double px = cx + (x1 * 1.5 * scale);
    double py = cy - (y2 * 1.5 * scale);

    return Offset(px, py);
  }

  @override
  bool shouldRepaint(covariant _BimModelPainter oldDelegate) {
    return oldDelegate.rotX != rotX ||
        oldDelegate.rotY != rotY ||
        oldDelegate.scale != scale ||
        oldDelegate.clipHeight != clipHeight ||
        oldDelegate.showArch != showArch ||
        oldDelegate.showConcrete != showConcrete ||
        oldDelegate.showRoof != showRoof ||
        oldDelegate.showMep != showMep ||
        oldDelegate.showRebar != showRebar;
  }
}

class _Vec3 {
  final double x;
  final double y;
  final double z;
  const _Vec3(this.x, this.y, this.z);
}
