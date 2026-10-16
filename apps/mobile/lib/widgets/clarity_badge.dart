import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../core/i18n.dart';

class ClarityBadge extends StatelessWidget {
  final bool verified;
  final bool hasRestrictions;
  final int trustScore;
  final String locale;

  const ClarityBadge({
    super.key,
    required this.verified,
    required this.hasRestrictions,
    required this.trustScore,
    this.locale = 'ru',
  });

  @override
  Widget build(BuildContext context) {
    Color bg;
    Color border;
    Color dotColor;
    Color textColor;
    String text;

    if (verified && !hasRestrictions) {
      bg = AnyqColors.clarityBg;
      border = const Color(0x66059669);
      dotColor = AnyqColors.clarity;
      textColor = const Color(0xFF065F46);
      text = AnyqI18n.t('verdictClear', locale: locale);
    } else if (verified && hasRestrictions) {
      bg = AnyqColors.cautionBg;
      border = const Color(0x66B45309);
      dotColor = AnyqColors.caution;
      textColor = const Color(0xFF92400E);
      text = AnyqI18n.t('verdictCaution', locale: locale);
    } else {
      bg = const Color(0xFFF1F5F9);
      border = const Color(0xFFCBD5E1);
      dotColor = AnyqColors.inkMute;
      textColor = AnyqColors.inkMute;
      text = AnyqI18n.t('unverified', locale: locale);
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: border, width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(
              color: dotColor,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              text,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: textColor,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.2,
              ),
            ),
          ),
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: border.withValues(alpha: 0.5), width: 0.8),
            ),
            child: Text(
              '$trustScore%',
              style: TextStyle(
                color: textColor,
                fontSize: 10,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
