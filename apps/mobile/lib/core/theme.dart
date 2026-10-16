import 'package:flutter/material.dart';

class AnyqColors {
  // Brand & Cadastre Primary
  static const Color primary = Color(0xFF0F2942);
  static const Color primaryLight = Color(0xFF1E3A8A);
  static const Color primaryAccent = Color(0xFF2F5B8A);

  // Surface & Paper
  static const Color canvas = Color(0xFFF8FAFC);
  static const Color paper = Color(0xFFEFE8DE);
  static const Color earth = Color(0xFFC9A882);
  static const Color terracotta = Color(0xFFB56A43);

  // Status Colors (Clarity system)
  static const Color clarity = Color(0xFF059669); // Участок ясен
  static const Color clarityBg = Color(0xFFECFDF5);
  static const Color caution = Color(0xFFB45309); // Нюансы/обременения
  static const Color cautionBg = Color(0xFFFFFBEB);
  static const Color danger = Color(0xFFDC2626);
  static const Color dangerBg = Color(0xFFFEF2F2);
  static const Color gold = Color(0xFFD4AF37);

  // Text / Ink
  static const Color ink = Color(0xFF0B132B);
  static const Color inkMute = Color(0xFF64748B);
  static const Color inkLight = Color(0xFF94A3B8);

  // Glass levels (L1, L2, L3)
  static const Color glassFillL1 = Color(0xCCFFFFFF);
  static const Color glassBorderL1 = Color(0x66E2E8F0);
  static const Color glassFillL2 = Color(0xF2FFFFFF);
  static const Color glassBorderL2 = Color(0x99CBD5E1);
  static const Color glassFillL3 = Color(0xFFFFFFFF);

  // Dark Canvas
  static const Color darkCanvas = Color(0xFF0B111E);
  static const Color darkSurface = Color(0xFF151E2E);
  static const Color darkBorder = Color(0xFF1E293B);
  static const Color darkInk = Color(0xFFF1F5F9);
  static const Color darkInkMute = Color(0xFF94A3B8);
}

class AnyqTheme {
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      scaffoldBackgroundColor: AnyqColors.canvas,
      primaryColor: AnyqColors.primary,
      colorScheme: ColorScheme.light(
        primary: AnyqColors.primary,
        secondary: AnyqColors.gold,
        surface: Colors.white,
        onSurface: AnyqColors.ink,
      ),
      fontFamily: 'Roboto',
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
        iconTheme: IconThemeData(color: AnyqColors.ink),
        titleTextStyle: TextStyle(
          color: AnyqColors.ink,
          fontSize: 18,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.3,
        ),
      ),
      cardTheme: CardThemeData(
        color: AnyqColors.glassFillL2,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(color: AnyqColors.glassBorderL1, width: 1),
        ),
      ),
      dividerTheme: const DividerThemeData(
        color: Color(0xFFE2E8F0),
        thickness: 1,
        space: 1,
      ),
    );
  }

  // L1 glass decoration: top bars, filter chips
  static BoxDecoration glassL1({double radius = 16}) => BoxDecoration(
        color: AnyqColors.glassFillL1,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: AnyqColors.glassBorderL1, width: 1),
        boxShadow: const [
          BoxShadow(
            color: Color(0x0A0F172A),
            blurRadius: 16,
            offset: Offset(0, 4),
          ),
        ],
      );

  // L2 glass decoration: cards, module tiles
  static BoxDecoration glassL2({double radius = 22}) => BoxDecoration(
        color: AnyqColors.glassFillL2,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: AnyqColors.glassBorderL2, width: 1),
        boxShadow: const [
          BoxShadow(
            color: Color(0x100F172A),
            blurRadius: 24,
            offset: Offset(0, 8),
          ),
          BoxShadow(
            color: Color(0x060F172A),
            blurRadius: 6,
            offset: Offset(0, 1),
          ),
        ],
      );

  // L3 modal sheet decoration
  static BoxDecoration glassL3({double radius = 28}) => BoxDecoration(
        color: AnyqColors.glassFillL3,
        borderRadius: BorderRadius.vertical(top: Radius.circular(radius)),
        border: Border.all(color: const Color(0x30D4AF37), width: 1),
        boxShadow: const [
          BoxShadow(
            color: Color(0x240F172A),
            blurRadius: 40,
            offset: Offset(0, -6),
          ),
        ],
      );
}
