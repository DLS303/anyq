import 'package:flutter/material.dart';
import '../../core/theme.dart';
import '../../core/i18n.dart';
import '../../models/plot.dart';
import '../../providers/app_state.dart';
import '../../widgets/glass_container.dart';
import '../../widgets/clarity_badge.dart';

class PassportScreen extends StatelessWidget {
  final AppState state;

  const PassportScreen({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final plot = state.selectedPlot;
    final locale = state.locale;

    if (plot == null) {
      return Scaffold(
        backgroundColor: AnyqColors.canvas,
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.shield_outlined, size: 48, color: AnyqColors.inkMute),
              const SizedBox(height: 12),
              Text(
                locale == 'kk' ? 'Нысан таңдалмаған' : 'Объект не выбран',
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
              ),
              const SizedBox(height: 8),
              ElevatedButton(
                onPressed: () => state.setTab(0),
                child: Text(locale == 'kk' ? 'Витринаға өту' : 'Перейти в витрину'),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      backgroundColor: AnyqColors.canvas,
      appBar: AppBar(
        title: Text(
          locale == 'kk' ? 'САНДЫҚ ТӨЛҚҰЖАТ' : 'ЦИФРОВОЙ ПАСПОРТ РИСКА',
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, letterSpacing: 1.0),
        ),
        actions: [
          IconButton(
            icon: Icon(
              plot.isFavorite ? Icons.favorite : Icons.favorite_border,
              color: plot.isFavorite ? Colors.red : AnyqColors.ink,
            ),
            onPressed: () => state.toggleFavorite(plot),
          ),
          IconButton(
            icon: const Icon(Icons.share_outlined, color: AnyqColors.ink),
            onPressed: () {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(locale == 'kk' ? 'Сілтеме көшірілді' : 'Ссылка на паспорт скопирована'),
                  duration: const Duration(seconds: 2),
                ),
              );
            },
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.only(left: 16, right: 16, bottom: 110),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Plot Header Card
            GlassContainer(
              level: GlassLevel.l2,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0x180F2942),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          plot.maskedCadastral,
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            color: AnyqColors.primary,
                            fontWeight: FontWeight.w700,
                            fontSize: 13,
                          ),
                        ),
                      ),
                      ClarityBadge(
                        verified: plot.verified,
                        hasRestrictions: plot.hasRestrictions,
                        trustScore: plot.trustScore,
                        locale: locale,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    plot.title(locale),
                    style: const TextStyle(
                      color: AnyqColors.ink,
                      fontWeight: FontWeight.w800,
                      fontSize: 20,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${plot.district} · ${plot.areaSotka} соток · ${plot.landCategory}',
                    style: const TextStyle(color: AnyqColors.inkMute, fontSize: 13),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    '${_formatPrice(plot.priceKzt)} ₸',
                    style: const TextStyle(
                      color: AnyqColors.primary,
                      fontWeight: FontWeight.w900,
                      fontSize: 24,
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Kaspi Report Purchase Banner / Unlocked Pill
            if (!plot.isUnlocked)
              Container(
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFFF14635), Color(0xFFE52E20)], // Kaspi Red
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(20),
                  boxShadow: const [
                    BoxShadow(color: Color(0x30E52E20), blurRadius: 18, offset: Offset(0, 6)),
                  ],
                ),
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: const BoxDecoration(
                        color: Colors.white,
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.lock_open, color: Color(0xFFE52E20), size: 22),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            locale == 'kk' ? 'ANYQ анықтық есебі' : 'Полный отчёт ясности ANYQ',
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 14,
                            ),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            locale == 'kk'
                                ? 'Кадастр нөмірін, ЕГКН көшірмесін және шектеулерді ашу'
                                : 'Раскрыть кадастр, выписку ЕГКН и координаты границ',
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.9),
                              fontSize: 11,
                            ),
                          ),
                        ],
                      ),
                    ),
                    ElevatedButton(
                      onPressed: () => _showKaspiPaySheet(context, plot, state, locale),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.white,
                        foregroundColor: const Color(0xFFE52E20),
                        elevation: 0,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      ),
                      child: Text(
                        '3 900 ₸',
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13),
                      ),
                    ),
                  ],
                ),
              )
            else
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFFECFDF5),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFF10B981), width: 1.2),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.check_circle, color: Color(0xFF059669), size: 24),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            locale == 'kk' ? 'Есеп ашылды және тексерілді' : 'Отчёт ясности оплачен и проверен',
                            style: const TextStyle(
                              color: Color(0xFF065F46),
                              fontWeight: FontWeight.w700,
                              fontSize: 13,
                            ),
                          ),
                          Text(
                            'Кадастровый номер: ${plot.cadastralNo}',
                            style: const TextStyle(
                              fontFamily: 'monospace',
                              color: Color(0xFF047857),
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

            const SizedBox(height: 18),

            // Legal Risks & Zones Section
            _buildSectionTitle(locale == 'kk' ? 'Құқықтық шектеулер мен аймақтар' : 'Юридические ограничения и зоны'),
            const SizedBox(height: 8),
            GlassContainer(
              level: GlassLevel.l2,
              child: Column(
                children: [
                  _buildRiskRow(
                    icon: Icons.terrain,
                    title: locale == 'kk' ? 'Сейсмикалық белдеу' : 'Сейсмическая зона',
                    value: locale == 'kk' ? '9–10 балл (Алматы)' : '9–10 баллов (Алматы)',
                    isRisk: false,
                    info: 'Требуется антисейсмический пояс и усиленный монолитный каркас.',
                  ),
                  const Divider(height: 16),
                  _buildRiskRow(
                    icon: Icons.linear_scale,
                    title: locale == 'kk' ? 'Қызыл сызықтар' : 'Красные линии дорог',
                    value: plot.redLines
                        ? (locale == 'kk' ? 'Шектеу бар (Генплан)' : 'Пересечение с генпланом!')
                        : (locale == 'kk' ? 'Таза' : 'Не пересекает'),
                    isRisk: plot.redLines,
                    info: plot.redLines ? 'Часть объекта попадает под расширение дороги по ПДП.' : 'Чисто.',
                  ),
                  const Divider(height: 16),
                  _buildRiskRow(
                    icon: Icons.water,
                    title: locale == 'kk' ? 'Су қорғау белдеуі' : 'Водоохранная полоса',
                    value: plot.waterProtection ? 'Ограничение' : 'Отсутствует',
                    isRisk: plot.waterProtection,
                  ),
                  const Divider(height: 16),
                  _buildRiskRow(
                    icon: Icons.electrical_services,
                    title: locale == 'kk' ? 'ЖЭЖ қорғау аймағы' : 'Охранная зона ЛЭП',
                    value: plot.powerProtectionZone ? 'Ограничение ЛЭП' : 'Отсутствует',
                    isRisk: plot.powerProtectionZone,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // Engineering Utilities Section
            _buildSectionTitle(locale == 'kk' ? 'Инженерлік желілер' : 'Инженерные сети и техусловия'),
            const SizedBox(height: 8),
            GlassContainer(
              level: GlassLevel.l2,
              child: Column(
                children: [
                  _buildUtilityRow(Icons.bolt, 'Электричество', plot.electricity, locale),
                  const Divider(height: 14),
                  _buildUtilityRow(Icons.local_fire_department, 'Газ (магистральный)', plot.gas, locale),
                  const Divider(height: 14),
                  _buildUtilityRow(Icons.water_drop, 'Водоснабжение', plot.water, locale),
                  const Divider(height: 14),
                  _buildUtilityRow(Icons.alt_route, 'Подъездной путь', plot.accessRoad, locale),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // Order Services Section (Surveyor, PSD, Architect)
            _buildSectionTitle(locale == 'kk' ? 'Қызметтерге тапсырыс беру' : 'Заказ сертифицированных услуг'),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: _buildServiceCard(
                    icon: Icons.architecture,
                    title: locale == 'kk' ? 'Геодезист' : 'Выезд геодезиста',
                    price: '35 000 ₸',
                    onTap: () => _showOrderServiceDialog(context, 'Выезд геодезиста для выноса точек в натуру', locale),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _buildServiceCard(
                    icon: Icons.design_services,
                    title: locale == 'kk' ? 'ЖСҚ тапсырыс' : 'Разработка ПСД',
                    price: '280 000 ₸',
                    onTap: () => _showOrderServiceDialog(context, 'Индивидуальный проект дома (АР + КР)', locale),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(
      title,
      style: const TextStyle(
        color: AnyqColors.primary,
        fontSize: 15,
        fontWeight: FontWeight.w800,
        letterSpacing: 0.2,
      ),
    );
  }

  Widget _buildRiskRow({
    required IconData icon,
    required String title,
    required String value,
    required bool isRisk,
    String? info,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 20, color: isRisk ? AnyqColors.danger : AnyqColors.primary),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AnyqColors.ink)),
              if (info != null)
                Text(info, style: const TextStyle(fontSize: 11, color: AnyqColors.inkMute)),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: isRisk ? const Color(0xFFFEE2E2) : const Color(0xFFECFDF5),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text(
            value,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: isRisk ? const Color(0xFFB91C1C) : const Color(0xFF047857),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildUtilityRow(IconData icon, String name, String status, String locale) {
    String statusLabel;
    Color statusColor;

    if (status == 'connected') {
      statusLabel = AnyqI18n.t('statusConnected', locale: locale);
      statusColor = AnyqColors.clarity;
    } else if (status == 'nearby') {
      statusLabel = AnyqI18n.t('statusNearby', locale: locale);
      statusColor = AnyqColors.caution;
    } else if (status == 'tu_received') {
      statusLabel = AnyqI18n.t('statusTu', locale: locale);
      statusColor = const Color(0xFF2563EB);
    } else {
      statusLabel = AnyqI18n.t('statusAbsent', locale: locale);
      statusColor = AnyqColors.inkMute;
    }

    return Row(
      children: [
        Icon(icon, size: 18, color: AnyqColors.primary),
        const SizedBox(width: 10),
        Expanded(
          child: Text(name, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AnyqColors.ink)),
        ),
        Text(
          statusLabel,
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: statusColor),
        ),
      ],
    );
  }

  Widget _buildServiceCard({
    required IconData icon,
    required String title,
    required String price,
    required VoidCallback onTap,
  }) {
    return GlassContainer(
      level: GlassLevel.l2,
      onTap: onTap,
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: AnyqColors.primary, size: 24),
          const SizedBox(height: 8),
          Text(title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AnyqColors.ink)),
          const SizedBox(height: 4),
          Text(price, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: AnyqColors.primary)),
        ],
      ),
    );
  }

  void _showKaspiPaySheet(BuildContext context, Plot plot, AppState state, String locale) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        return Container(
          decoration: AnyqTheme.glassL3(),
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(color: const Color(0xFFCBD5E1), borderRadius: BorderRadius.circular(2)),
              ),
              const SizedBox(height: 18),
              const Text(
                'Kaspi Pay · Оплата отчёта',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Color(0xFFE52E20)),
              ),
              const SizedBox(height: 6),
              Text(
                'Раскрытие юридического паспорта объекта ${plot.title(locale)}',
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 13, color: AnyqColors.inkMute),
              ),
              const SizedBox(height: 20),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFFE2E8F0)),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: const [
                    Text('Сумма к списанию:', style: TextStyle(fontWeight: FontWeight.w600)),
                    Text(
                      '3 900 ₸',
                      style: TextStyle(fontWeight: FontWeight.w900, fontSize: 20, color: Color(0xFFE52E20)),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton(
                  onPressed: () {
                    Navigator.pop(ctx);
                    state.unlockPlotReport(plot);
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        backgroundColor: Color(0xFF059669),
                        content: Text('Успешно! Отчёт оплачен. Кадастровый номер раскрыт.'),
                      ),
                    );
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFFE52E20),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  ),
                  child: const Text('Оплатить через Kaspi Pay', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                ),
              ),
              const SizedBox(height: 12),
            ],
          ),
        );
      },
    );
  }

  void _showOrderServiceDialog(BuildContext context, String serviceName, String locale) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: Text(locale == 'kk' ? 'Тапсырыс' : 'Оформление заявки'),
        content: Text('Вы действительно хотите заказать: $serviceName?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Отмена')),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  backgroundColor: AnyqColors.primary,
                  content: Text('Заявка принята! Специалист свяжется с вами в течение 15 минут.'),
                ),
              );
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: AnyqColors.primary,
              foregroundColor: Colors.white,
            ),
            child: const Text('Подтвердить'),
          ),
        ],
      ),
    );
  }

  String _formatPrice(int price) {
    return price.toString().replaceAllMapped(
          RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'),
          (Match m) => '${m[1]} ',
        );
  }
}
