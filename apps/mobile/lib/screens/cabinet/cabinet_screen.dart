import 'package:flutter/material.dart';
import '../../core/theme.dart';
import '../../core/i18n.dart';
import '../../providers/app_state.dart';
import '../../widgets/glass_container.dart';

class CabinetScreen extends StatelessWidget {
  final AppState state;

  const CabinetScreen({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final locale = state.locale;
    final role = state.currentRole;
    final favoritePlots = state.plots.where((p) => p.isFavorite).toList();

    return Scaffold(
      backgroundColor: AnyqColors.canvas,
      appBar: AppBar(
        title: Text(
          locale == 'kk' ? 'ЖЕКЕ КАБИНЕТ ЖӘНЕ CRM' : 'ЛИЧНЫЙ КАБИНЕТ И CRM',
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, letterSpacing: 1.0),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.only(left: 16, right: 16, bottom: 110),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // User Profile Card
            GlassContainer(
              level: GlassLevel.l2,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 52,
                        height: 52,
                        decoration: const BoxDecoration(
                          color: AnyqColors.primary,
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.person, color: AnyqColors.gold, size: 28),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Амир Куандыков',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w800,
                                color: AnyqColors.ink,
                              ),
                            ),
                            Text(
                              '$role@demo.superapp',
                              style: const TextStyle(fontSize: 12, color: AnyqColors.inkMute),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0x20D4AF37),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: AnyqColors.gold),
                        ),
                        child: Text(
                          _getRoleLabel(role, locale),
                          style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w800,
                            color: AnyqColors.primary,
                          ),
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 16),
                  const Divider(height: 1),
                  const SizedBox(height: 12),

                  // Demo Role Quick Switcher
                  Text(
                    locale == 'kk' ? 'Демо рөлді ауыстыру' : 'Быстрое переключение роли (демо):',
                    style: const TextStyle(fontSize: 12, color: AnyqColors.inkMute, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      _buildRoleChip('buyer', 'Покупатель', role, state),
                      _buildRoleChip('owner', 'Продавец', role, state),
                      _buildRoleChip('moderator', 'Модератор', role, state),
                      _buildRoleChip('admin', 'Админ', role, state),
                    ],
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // Favorites Section
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  locale == 'kk' ? 'Таңдаулы нысандар' : 'Избранные объекты',
                  style: const TextStyle(color: AnyqColors.primary, fontSize: 15, fontWeight: FontWeight.w800),
                ),
                Text(
                  '${favoritePlots.length}',
                  style: const TextStyle(color: AnyqColors.inkMute, fontWeight: FontWeight.w700),
                ),
              ],
            ),
            const SizedBox(height: 8),

            if (favoritePlots.isEmpty)
              GlassContainer(
                level: GlassLevel.l1,
                padding: const EdgeInsets.all(16),
                child: Center(
                  child: Text(
                    locale == 'kk' ? 'Әзірге таңдаулылар жоқ' : 'В избранном пока нет объектов',
                    style: const TextStyle(fontSize: 13, color: AnyqColors.inkMute),
                  ),
                ),
              )
            else
              Column(
                children: favoritePlots.map((plot) {
                  return Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: GlassContainer(
                      level: GlassLevel.l2,
                      padding: const EdgeInsets.all(12),
                      onTap: () => state.selectPlot(plot),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  plot.title(locale),
                                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
                                ),
                                Text(
                                  '${plot.district} · ${plot.areaSotka} сот.',
                                  style: const TextStyle(color: AnyqColors.inkMute, fontSize: 11),
                                ),
                              ],
                            ),
                          ),
                          Text(
                            '${_formatPrice(plot.priceKzt)} ₸',
                            style: const TextStyle(
                              color: AnyqColors.primary,
                              fontWeight: FontWeight.w800,
                              fontSize: 13,
                            ),
                          ),
                          const SizedBox(width: 8),
                          const Icon(Icons.arrow_forward_ios, size: 12, color: AnyqColors.inkMute),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ),

            const SizedBox(height: 18),

            // CRM Pipeline Section
            Text(
              locale == 'kk' ? 'CRM воронкасы және мәмілелер' : 'CRM Воронка и сделки девелопмента',
              style: const TextStyle(color: AnyqColors.primary, fontSize: 15, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 8),

            GlassContainer(
              level: GlassLevel.l2,
              child: Column(
                children: [
                  _buildCrmDealRow(
                    dealNo: 'Сделка №104',
                    title: 'Покупка ИЖС Бесагаш (8.4 сот)',
                    status: 'Эскроу открыт',
                    amount: '28 500 000 ₸',
                    statusColor: AnyqColors.clarity,
                  ),
                  const Divider(height: 16),
                  _buildCrmDealRow(
                    dealNo: 'Сделка №108',
                    title: 'Разработка ПСД и топосъемка',
                    status: 'В работе генподрядчика',
                    amount: '315 000 ₸',
                    statusColor: const Color(0xFF2563EB),
                  ),
                  const Divider(height: 16),
                  _buildCrmDealRow(
                    dealNo: 'Сделка №112',
                    title: 'Поставка бетона М350 (48 м³)',
                    status: 'Доставка на площадку',
                    amount: '1 820 000 ₸',
                    statusColor: AnyqColors.caution,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // Moderator Queue (If moderator/admin)
            if (role == 'moderator' || role == 'admin') ...[
              Text(
                locale == 'kk' ? 'Модерация кезегі' : 'Очередь модерации',
                style: const TextStyle(color: AnyqColors.primary, fontSize: 15, fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 8),
              GlassContainer(
                level: GlassLevel.l2,
                child: Column(
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.pending_actions, color: AnyqColors.caution),
                        const SizedBox(width: 8),
                        const Expanded(
                          child: Text(
                            'ИЖС Наурызбай (8 сот) — проверка кадастра',
                            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: () {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('Отправлено на доработку продавцу')),
                              );
                            },
                            style: OutlinedButton.styleFrom(
                              foregroundColor: AnyqColors.caution,
                              side: const BorderSide(color: AnyqColors.caution),
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                            ),
                            child: const Text('На доработку', style: TextStyle(fontSize: 11)),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: ElevatedButton(
                            onPressed: () {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  backgroundColor: AnyqColors.clarity,
                                  content: Text('Объект проверен и опубликован!'),
                                ),
                              );
                            },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AnyqColors.clarity,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                            ),
                            child: const Text('Одобрить', style: TextStyle(fontSize: 11)),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 18),
            ],

            // App Information & Version
            Center(
              child: Column(
                children: [
                  const Text(
                    'ANYQ Mobile · ConTech SuperApp v1.0.0',
                    style: TextStyle(fontSize: 11, color: AnyqColors.inkMute, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 2),
                  const Text(
                    'Республика Казахстан · Алматы 2026',
                    style: TextStyle(fontSize: 10, color: AnyqColors.inkLight),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRoleChip(String r, String label, String current, AppState state) {
    final active = r == current;
    return GestureDetector(
      onTap: () => state.setRole(r),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: active ? AnyqColors.primary : const Color(0xFFF1F5F9),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: active ? AnyqColors.primary : const Color(0xFFE2E8F0)),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11,
            fontWeight: active ? FontWeight.w700 : FontWeight.w500,
            color: active ? Colors.white : AnyqColors.ink,
          ),
        ),
      ),
    );
  }

  Widget _buildCrmDealRow({
    required String dealNo,
    required String title,
    required String status,
    required String amount,
    required Color statusColor,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(dealNo, style: const TextStyle(fontSize: 11, color: AnyqColors.inkMute, fontWeight: FontWeight.w700)),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: statusColor.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                status,
                style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: statusColor),
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13, color: AnyqColors.ink)),
        const SizedBox(height: 2),
        Text(amount, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13, color: AnyqColors.primary)),
      ],
    );
  }

  String _getRoleLabel(String r, String locale) {
    switch (r) {
      case 'owner':
        return locale == 'kk' ? 'Сатушы' : 'Продавец';
      case 'moderator':
        return locale == 'kk' ? 'Модератор' : 'Модератор';
      case 'admin':
        return locale == 'kk' ? 'Әкімші' : 'Администратор';
      default:
        return locale == 'kk' ? 'Сатып алушы' : 'Покупатель';
    }
  }

  String _formatPrice(int price) {
    return price.toString().replaceAllMapped(
          RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'),
          (Match m) => '${m[1]} ',
        );
  }
}
