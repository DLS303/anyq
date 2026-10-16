import 'package:flutter/material.dart';
import '../../core/theme.dart';
import '../../core/i18n.dart';
import '../../models/site_project.dart';
import '../../providers/app_state.dart';
import '../../widgets/glass_container.dart';
import '../../widgets/bim_viewer_3d.dart';

class SiteScreen extends StatelessWidget {
  final AppState state;

  const SiteScreen({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final project = state.siteProject;
    final locale = state.locale;

    return Scaffold(
      backgroundColor: AnyqColors.canvas,
      appBar: AppBar(
        title: Text(
          locale == 'kk' ? 'ЦИФРЛЫҚ ҚҰРЫЛЫС АЛАҢЫ' : 'ЦИФРОВАЯ СТРОЙПЛОЩАДКА',
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, letterSpacing: 1.0),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.only(bottom: 110),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Project Header Card
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: GlassContainer(
                level: GlassLevel.l2,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          project.title(locale),
                          style: const TextStyle(
                            color: AnyqColors.ink,
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: const Color(0xFFECFDF5),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: const Color(0xFF059669)),
                          ),
                          child: Text(
                            '${(project.totalProgress * 100).round()}% готовности',
                            style: const TextStyle(
                              color: Color(0xFF047857),
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      project.address,
                      style: const TextStyle(color: AnyqColors.inkMute, fontSize: 13),
                    ),
                    const SizedBox(height: 12),
                    LinearProgressIndicator(
                      value: project.totalProgress,
                      backgroundColor: const Color(0xFFE2E8F0),
                      valueColor: const AlwaysStoppedAnimation<Color>(AnyqColors.primary),
                      minHeight: 6,
                      borderRadius: BorderRadius.circular(3),
                    ),
                  ],
                ),
              ),
            ),

            const SizedBox(height: 16),

            // 3D BIM Model Section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                locale == 'kk' ? 'Интерактивті 3D BIM үлгісі' : 'Интерактивная 3D BIM модель объекта',
                style: const TextStyle(
                  color: AnyqColors.primary,
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(height: 8),

            BimViewer3D(projectTitle: project.title(locale)),

            const SizedBox(height: 20),

            // Gantt Chart / Milestones Section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                locale == 'kk' ? 'Гант кестесі (кезеңдер)' : 'График Ганта и этапы строительства',
                style: const TextStyle(
                  color: AnyqColors.primary,
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(height: 8),

            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: GlassContainer(
                level: GlassLevel.l2,
                child: Column(
                  children: project.stages.map((stage) {
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    stage.isCompleted
                                        ? Icons.check_circle
                                        : (stage.progress > 0 ? Icons.timelapse : Icons.radio_button_unchecked),
                                    size: 16,
                                    color: stage.isCompleted
                                        ? AnyqColors.clarity
                                        : (stage.progress > 0 ? AnyqColors.caution : AnyqColors.inkMute),
                                  ),
                                  const SizedBox(width: 8),
                                  Text(
                                    stage.title(locale),
                                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AnyqColors.ink),
                                  ),
                                ],
                              ),
                              Text(
                                '${(stage.progress * 100).round()}%',
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700,
                                  color: stage.isCompleted ? AnyqColors.clarity : AnyqColors.primary,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 4),
                          LinearProgressIndicator(
                            value: stage.progress,
                            backgroundColor: const Color(0xFFE2E8F0),
                            valueColor: AlwaysStoppedAnimation<Color>(
                              stage.isCompleted ? AnyqColors.clarity : AnyqColors.primary,
                            ),
                            minHeight: 4,
                            borderRadius: BorderRadius.circular(2),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            '${stage.startDate} — ${stage.endDate}',
                            style: const TextStyle(fontSize: 10, color: AnyqColors.inkMute),
                          ),
                        ],
                      ),
                    );
                  }).toList(),
                ),
              ),
            ),

            const SizedBox(height: 20),

            // KS-2 / KS-3 Acts & Digital Signature Section
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                locale == 'kk' ? 'КС-2 / КС-3 қабылдау актілері' : 'Электронные акты КС-2 / КС-3',
                style: const TextStyle(
                  color: AnyqColors.primary,
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(height: 8),

            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: GlassContainer(
                level: GlassLevel.l2,
                child: Column(
                  children: project.acts.map((act) {
                    return Container(
                      margin: const EdgeInsets.symmetric(vertical: 6),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: const Color(0xFFE2E8F0)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: const Color(0x180F2942),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Text(
                                  act.actNo,
                                  style: const TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w700,
                                    color: AnyqColors.primary,
                                  ),
                                ),
                              ),
                              Text(act.date, style: const TextStyle(fontSize: 11, color: AnyqColors.inkMute)),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Text(
                            act.title(locale),
                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AnyqColors.ink),
                          ),
                          const SizedBox(height: 8),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                '${_formatPrice(act.amountKzt)} ₸',
                                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: AnyqColors.primary),
                              ),
                              if (act.isSigned)
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFECFDF5),
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(color: const Color(0xFF059669)),
                                  ),
                                  child: Row(
                                    children: [
                                      const Icon(Icons.verified, size: 12, color: AnyqColors.clarity),
                                      const SizedBox(width: 4),
                                      Text(
                                        locale == 'kk' ? 'Қол қойылды' : 'Подписан сторонами',
                                        style: const TextStyle(
                                          fontSize: 11,
                                          fontWeight: FontWeight.w700,
                                          color: Color(0xFF047857),
                                        ),
                                      ),
                                    ],
                                  ),
                                )
                              else
                                ElevatedButton.icon(
                                  onPressed: () => _showSignModal(context, act, state, locale),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: AnyqColors.primary,
                                    foregroundColor: Colors.white,
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                    elevation: 0,
                                  ),
                                  icon: const Icon(Icons.draw, size: 14),
                                  label: Text(
                                    locale == 'kk' ? 'Қол қою' : 'Подписать акт',
                                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
                                  ),
                                ),
                            ],
                          ),
                        ],
                      ),
                    );
                  }).toList(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showSignModal(BuildContext context, KsAct act, AppState state, String locale) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
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
              Text(
                'Подписание ${act.actNo}',
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AnyqColors.primary),
              ),
              const SizedBox(height: 4),
              Text(
                act.title(locale),
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 12, color: AnyqColors.inkMute),
              ),
              const SizedBox(height: 16),

              // Digital Signature canvas area
              Container(
                height: 130,
                width: double.infinity,
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFFCBD5E1)),
                ),
                child: Stack(
                  children: [
                    Center(
                      child: Text(
                        'Поле электронной подписи заказчика',
                        style: TextStyle(color: Colors.grey.shade400, fontSize: 13),
                      ),
                    ),
                    Positioned(
                      bottom: 8,
                      right: 12,
                      child: Row(
                        children: const [
                          Icon(Icons.fingerprint, size: 16, color: AnyqColors.primary),
                          SizedBox(width: 4),
                          Text('ANYQ Secure Sign v2.1', style: TextStyle(fontSize: 10, color: AnyqColors.inkMute)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 20),

              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: () {
                    Navigator.pop(ctx);
                    state.signKsAct(act.id);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        backgroundColor: AnyqColors.clarity,
                        content: Text('Акт ${act.actNo} успешно подписан ЭЦП!'),
                      ),
                    );
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AnyqColors.primary,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  ),
                  child: const Text('Подтвердить подписание акта', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  String _formatPrice(int price) {
    return price.toString().replaceAllMapped(
          RegExp(r'(\d{1,3})(?=(\d{3})+(?!\d))'),
          (Match m) => '${m[1]} ',
        );
  }
}
