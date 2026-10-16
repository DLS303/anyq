import 'package:flutter/material.dart';
import '../core/theme.dart';
import '../core/i18n.dart';

class LuxuryNavBar extends StatelessWidget {
  final int currentIndex;
  final Function(int) onTabSelected;
  final String locale;

  const LuxuryNavBar({
    super.key,
    required this.currentIndex,
    required this.onTabSelected,
    required this.locale,
  });

  @override
  Widget build(BuildContext context) {
    final items = [
      {'label': AnyqI18n.t('navCatalog', locale: locale), 'icon': Icons.explore_outlined, 'activeIcon': Icons.explore},
      {'label': AnyqI18n.t('navPassport', locale: locale), 'icon': Icons.shield_outlined, 'activeIcon': Icons.shield},
      {'label': AnyqI18n.t('navEstimates', locale: locale), 'icon': Icons.calculate_outlined, 'activeIcon': Icons.calculate},
      {'label': AnyqI18n.t('navSite', locale: locale), 'icon': Icons.domain_outlined, 'activeIcon': Icons.domain},
      {'label': AnyqI18n.t('navCabinet', locale: locale), 'icon': Icons.person_outline, 'activeIcon': Icons.person},
    ];

    return SafeArea(
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
        decoration: BoxDecoration(
          color: const Color(0xF20F2942), // Luxury dark glass
          borderRadius: BorderRadius.circular(30),
          border: Border.all(color: const Color(0x33D4AF37), width: 1.2), // Gold sheen
          boxShadow: const [
            BoxShadow(
              color: Color(0x330B132B),
              blurRadius: 28,
              offset: Offset(0, 10),
            ),
          ],
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: List.generate(items.length, (index) {
            final isSelected = currentIndex == index;
            final item = items[index];

            return GestureDetector(
              onTap: () => onTabSelected(index),
              behavior: HitTestBehavior.opaque,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                curve: Curves.easeOutCubic,
                padding: EdgeInsets.symmetric(
                  horizontal: isSelected ? 12 : 8,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: isSelected ? const Color(0x28D4AF37) : Colors.transparent,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      isSelected ? (item['activeIcon'] as IconData) : (item['icon'] as IconData),
                      color: isSelected ? AnyqColors.gold : Colors.white.withValues(alpha: 0.7),
                      size: 22,
                    ),
                    const SizedBox(height: 3),
                    Text(
                      item['label'] as String,
                      style: TextStyle(
                        color: isSelected ? AnyqColors.gold : Colors.white.withValues(alpha: 0.65),
                        fontSize: 10,
                        fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
