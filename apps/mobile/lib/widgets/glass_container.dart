import 'package:flutter/material.dart';
import '../core/theme.dart';

enum GlassLevel { l1, l2, l3 }

class GlassContainer extends StatelessWidget {
  final Widget child;
  final GlassLevel level;
  final double radius;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final VoidCallback? onTap;
  final Border? customBorder;

  const GlassContainer({
    super.key,
    required this.child,
    this.level = GlassLevel.l2,
    this.radius = 20,
    this.padding,
    this.margin,
    this.onTap,
    this.customBorder,
  });

  @override
  Widget build(BuildContext context) {
    Color bg;
    Border border;
    List<BoxShadow> shadows;

    switch (level) {
      case GlassLevel.l1:
        bg = AnyqColors.glassFillL1;
        border = customBorder ?? Border.all(color: AnyqColors.glassBorderL1, width: 1);
        shadows = const [
          BoxShadow(
            color: Color(0x080F172A),
            blurRadius: 16,
            offset: Offset(0, 4),
          ),
        ];
        break;
      case GlassLevel.l2:
        bg = AnyqColors.glassFillL2;
        border = customBorder ?? Border.all(color: AnyqColors.glassBorderL2, width: 1);
        shadows = const [
          BoxShadow(
            color: Color(0x0C0F172A),
            blurRadius: 22,
            offset: Offset(0, 8),
          ),
          BoxShadow(
            color: Color(0x040F172A),
            blurRadius: 4,
            offset: Offset(0, 1),
          ),
        ];
        break;
      case GlassLevel.l3:
        bg = AnyqColors.glassFillL3;
        border = customBorder ?? Border.all(color: const Color(0x33D4AF37), width: 1.2);
        shadows = const [
          BoxShadow(
            color: Color(0x200F172A),
            blurRadius: 36,
            offset: Offset(0, 12),
          ),
        ];
        break;
    }

    Widget content = Container(
      margin: margin,
      padding: padding ?? const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(radius),
        border: border,
        boxShadow: shadows,
      ),
      child: child,
    );

    if (onTap != null) {
      return Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(radius),
          onTap: onTap,
          child: content,
        ),
      );
    }

    return content;
  }
}
