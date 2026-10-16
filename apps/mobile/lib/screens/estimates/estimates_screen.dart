import 'package:flutter/material.dart';
import '../../core/theme.dart';
import '../../core/i18n.dart';
import '../../models/estimate.dart';
import '../../providers/app_state.dart';
import '../../widgets/glass_container.dart';

class EstimatesScreen extends StatefulWidget {
  final AppState state;

  const EstimatesScreen({super.key, required this.state});

  @override
  State<EstimatesScreen> createState() => _EstimatesScreenState();
}

class _EstimatesScreenState extends State<EstimatesScreen> {
  double areaM2 = 180.0;
  int floors = 2;
  String wallMaterial = 'gasoblock'; // 'brick', 'gasoblock', 'monolith'

  @override
  Widget build(BuildContext context) {
    final locale = widget.state.locale;
    final estimate = EstimateResult.calculate(
      areaM2: areaM2,
      floors: floors,
      wallMaterial: wallMaterial,
    );

    return Scaffold(
      backgroundColor: AnyqColors.canvas,
      appBar: AppBar(
        title: Text(
          locale == 'kk' ? 'СМЕТА КАЛЬКУЛЯТОРЫ' : 'КАЛЬКУЛЯТОР СМЕТЫ ДОМА',
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, letterSpacing: 1.0),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.only(left: 16, right: 16, bottom: 110),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Parameter Input Card
            GlassContainer(
              level: GlassLevel.l2,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        locale == 'kk' ? 'Үйдің ауданы' : 'Площадь дома',
                        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AnyqColors.ink),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: AnyqColors.primary,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          '${areaM2.round()} м²',
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w800,
                            fontSize: 14,
                          ),
                        ),
                      ),
                    ],
                  ),
                  Slider(
                    value: areaM2,
                    min: 80,
                    max: 450,
                    divisions: 37,
                    activeColor: AnyqColors.primary,
                    inactiveColor: const Color(0xFFE2E8F0),
                    onChanged: (val) => setState(() => areaM2 = val),
                  ),

                  const SizedBox(height: 10),

                  // Floors Selector
                  Text(
                    locale == 'kk' ? 'Қабаттылығы' : 'Этажность',
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AnyqColors.ink),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      _buildFloorOption(1, '1 этаж'),
                      const SizedBox(width: 8),
                      _buildFloorOption(2, '2 этажа'),
                      const SizedBox(width: 8),
                      _buildFloorOption(3, '3 этажа'),
                    ],
                  ),

                  const SizedBox(height: 14),

                  // Material Selector
                  Text(
                    locale == 'kk' ? 'Қабырға материалы' : 'Материал стен',
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AnyqColors.ink),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      _buildMaterialOption('gasoblock', 'Газоблок'),
                      const SizedBox(width: 8),
                      _buildMaterialOption('brick', 'Кирпич'),
                      const SizedBox(width: 8),
                      _buildMaterialOption('monolith', 'Монолит'),
                    ],
                  ),
                ],
              ),
            ),

            const SizedBox(height: 16),

            // Summary Result Card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFF0F2942), Color(0xFF1E3A8A)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(24),
                boxShadow: const [
                  BoxShadow(color: Color(0x330F2942), blurRadius: 20, offset: Offset(0, 8)),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        locale == 'kk' ? 'БОЛЖАМДЫ БАҒАСЫ' : 'ОРИЕНТИР СТОИМОСТИ',
                        style: const TextStyle(
                          color: AnyqColors.gold,
                          fontSize: 12,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 1.0,
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: const Color(0x33D4AF37),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          '${_formatPrice((estimate.totalKzt / areaM2).round())} ₸/м²',
                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    '${_formatPrice(estimate.totalKzt)} ₸',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 30,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    locale == 'kk'
                        ? 'Материалдар мен жұмыстың толық BOQ ведомосі'
                        : 'Комплекс СМР: материалы + строительно-монтажные работы',
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 12),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // Cost Structure Breakdown
            Text(
              locale == 'kk' ? 'Шығындар құрылымы' : 'Структура затрат по разделам',
              style: const TextStyle(
                color: AnyqColors.primary,
                fontSize: 15,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),

            GlassContainer(
              level: GlassLevel.l2,
              child: Column(
                children: [
                  _buildCostRow('Фундаментная плита и земляные работы', estimate.foundationKzt, estimate.totalKzt),
                  const Divider(height: 18),
                  _buildCostRow('Несущие стены, перекрытия и сейсмопояс', estimate.wallsKzt, estimate.totalKzt),
                  const Divider(height: 18),
                  _buildCostRow('Кровельная система и утепление', estimate.roofKzt, estimate.totalKzt),
                  const Divider(height: 18),
                  _buildCostRow('Инженерные сети (электрика, ОВ/ВК)', estimate.utilitiesKzt, estimate.totalKzt),
                  const Divider(height: 18),
                  _buildCostRow('Черновая стяжка и штукатурка', estimate.finishingKzt, estimate.totalKzt),
                ],
              ),
            ),

            const SizedBox(height: 18),

            // Itemized BOQ Bill of Quantities
            Text(
              locale == 'kk' ? 'Егжей-тегжейлі ведомость (BOQ)' : 'Детализированная ведомость (BOQ)',
              style: const TextStyle(
                color: AnyqColors.primary,
                fontSize: 15,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),

            GlassContainer(
              level: GlassLevel.l2,
              child: Column(
                children: estimate.items.map((item) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                item.title(locale),
                                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AnyqColors.ink),
                              ),
                              Text(
                                '${item.quantity.toStringAsFixed(1)} ${item.unit} × ${_formatPrice(item.unitPriceKzt)} ₸',
                                style: const TextStyle(fontSize: 11, color: AnyqColors.inkMute),
                              ),
                            ],
                          ),
                        ),
                        Text(
                          '${_formatPrice(item.totalKzt)} ₸',
                          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AnyqColors.primary),
                        ),
                      ],
                    ),
                  );
                }).toList(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFloorOption(int count, String label) {
    final selected = floors == count;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => floors = count),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: selected ? AnyqColors.primary : Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: selected ? AnyqColors.primary : const Color(0xFFCBD5E1)),
          ),
          child: Text(
            label,
            style: TextStyle(
              color: selected ? Colors.white : AnyqColors.ink,
              fontWeight: FontWeight.w700,
              fontSize: 12,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMaterialOption(String key, String label) {
    final selected = wallMaterial == key;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => wallMaterial = key),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: selected ? AnyqColors.primary : Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: selected ? AnyqColors.primary : const Color(0xFFCBD5E1)),
          ),
          child: Text(
            label,
            style: TextStyle(
              color: selected ? Colors.white : AnyqColors.ink,
              fontWeight: FontWeight.w700,
              fontSize: 12,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCostRow(String title, int amount, int total) {
    final pct = (amount / total * 100).round();
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AnyqColors.ink)),
              const SizedBox(height: 2),
              LinearProgressIndicator(
                value: amount / total,
                backgroundColor: const Color(0xFFE2E8F0),
                valueColor: const AlwaysStoppedAnimation<Color>(AnyqColors.primary),
                minHeight: 4,
                borderRadius: BorderRadius.circular(2),
              ),
            ],
          ),
        ),
        const SizedBox(width: 16),
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Text(
              '${_formatPrice(amount)} ₸',
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: AnyqColors.primary),
            ),
            Text(
              '$pct%',
              style: const TextStyle(fontSize: 11, color: AnyqColors.inkMute, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ],
    );
  }

  String _formatPrice(int price) {
    return price.toString().replaceAllMapped(
          RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'),
          (Match m) => '${m[1]} ',
        );
  }
}
