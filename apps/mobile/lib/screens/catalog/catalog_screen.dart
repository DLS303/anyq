import 'package:flutter/material.dart';
import '../../core/theme.dart';
import '../../core/i18n.dart';
import '../../models/plot.dart';
import '../../providers/app_state.dart';
import '../../widgets/glass_container.dart';
import '../../widgets/clarity_badge.dart';
import '../../widgets/interactive_cadastral_map.dart';

class CatalogScreen extends StatefulWidget {
  final AppState state;

  const CatalogScreen({super.key, required this.state});

  @override
  State<CatalogScreen> createState() => _CatalogScreenState();
}

class _CatalogScreenState extends State<CatalogScreen> {
  bool isMapView = true;
  final TextEditingController _searchCtrl = TextEditingController();

  final List<String> districts = [
    'Все районы',
    'Медеуский район',
    'Талгарский район',
    'Наурызбайский район',
    'Бостандыкский район',
  ];

  @override
  void initState() {
    super.initState();
    _searchCtrl.text = widget.state.searchQuery;
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    final locale = state.locale;

    return Scaffold(
      backgroundColor: AnyqColors.canvas,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            // Top Bar: Brand, Language Toggle & View Mode Toggle
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(
                children: [
                  // ANYQ Brand
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: AnyqColors.primary,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Text(
                          'ANYQ',
                          style: TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 1.5,
                            fontSize: 14,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        locale == 'kk' ? 'ЖЕР ВИТРИНАСЫ' : 'ВИТРИНА ЗЕМЛИ',
                        style: const TextStyle(
                          color: AnyqColors.primary,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.8,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                  const Spacer(),

                  // Language Switcher
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: const Color(0x33CBD5E1)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _buildLangBtn('ru', 'RU', locale),
                        _buildLangBtn('kk', 'KK', locale),
                      ],
                    ),
                  ),

                  const SizedBox(width: 8),

                  // Map/List toggle
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: const Color(0x33CBD5E1)),
                    ),
                    child: Row(
                      children: [
                        IconButton(
                          icon: Icon(
                            Icons.map,
                            size: 18,
                            color: isMapView ? AnyqColors.primary : const Color(0xFF94A3B8),
                          ),
                          onPressed: () => setState(() => isMapView = true),
                          constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                          padding: EdgeInsets.zero,
                        ),
                        IconButton(
                          icon: Icon(
                            Icons.view_agenda,
                            size: 18,
                            color: !isMapView ? AnyqColors.primary : const Color(0xFF94A3B8),
                          ),
                          onPressed: () => setState(() => isMapView = false),
                          constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                          padding: EdgeInsets.zero,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // Search Bar
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              child: Container(
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0x33CBD5E1)),
                  boxShadow: const [
                    BoxShadow(color: Color(0x06000000), blurRadius: 10, offset: Offset(0, 2)),
                  ],
                ),
                child: TextField(
                  controller: _searchCtrl,
                  onChanged: (val) => state.setSearchQuery(val),
                  decoration: InputDecoration(
                    hintText: AnyqI18n.t('searchPh', locale: locale),
                    hintStyle: const TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
                    prefixIcon: const Icon(Icons.search, size: 20, color: AnyqColors.primary),
                    suffixIcon: _searchCtrl.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, size: 18),
                            onPressed: () {
                              _searchCtrl.clear();
                              state.setSearchQuery('');
                            },
                          )
                        : null,
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                  ),
                ),
              ),
            ),

            // Filter Chips Carousel
            SizedBox(
              height: 44,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                children: [
                  // District Dropdown Chip
                  PopupMenuButton<String>(
                    onSelected: (val) {
                      state.setDistrict(val == 'Все районы' ? null : val);
                    },
                    itemBuilder: (ctx) => districts
                        .map((d) => PopupMenuItem(value: d, child: Text(d, style: const TextStyle(fontSize: 13))))
                        .toList(),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      decoration: BoxDecoration(
                        color: state.selectedDistrict != null ? AnyqColors.primary : Colors.white,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: const Color(0x33CBD5E1)),
                      ),
                      child: Row(
                        children: [
                          Text(
                            state.selectedDistrict ?? AnyqI18n.t('allDistricts', locale: locale),
                            style: TextStyle(
                              color: state.selectedDistrict != null ? Colors.white : AnyqColors.ink,
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(width: 4),
                          Icon(
                            Icons.arrow_drop_down,
                            size: 16,
                            color: state.selectedDistrict != null ? Colors.white : AnyqColors.ink,
                          ),
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(width: 6),

                  _buildFilterChip(
                    label: AnyqI18n.t('onlyVerified', locale: locale),
                    selected: state.filterOnlyVerified,
                    onTap: state.toggleVerified,
                  ),
                  const SizedBox(width: 6),

                  _buildFilterChip(
                    label: AnyqI18n.t('onlyGas', locale: locale),
                    selected: state.filterOnlyGas,
                    onTap: state.toggleGas,
                  ),
                  const SizedBox(width: 6),

                  _buildFilterChip(
                    label: AnyqI18n.t('onlyLight', locale: locale),
                    selected: state.filterOnlyLight,
                    onTap: state.toggleLight,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 6),

            // Content Area (Map view or List view)
            Expanded(
              child: isMapView
                  ? Stack(
                      children: [
                        // Map
                        Positioned.fill(
                          child: Padding(
                            padding: const EdgeInsets.only(left: 12, right: 12, bottom: 8),
                            child: InteractiveCadastralMap(
                              plots: state.plots,
                              selectedPlot: state.selectedPlot,
                              onPlotSelected: (p) => state.selectPlot(p),
                            ),
                          ),
                        ),

                        // Bottom Floating Cards Carousel
                        Positioned(
                          left: 0,
                          right: 0,
                          bottom: 12,
                          height: 185,
                          child: state.plots.isEmpty
                              ? Center(
                                  child: GlassContainer(
                                    child: Text(
                                      locale == 'kk' ? 'Телімдер табылмады' : 'Участки не найдены',
                                      style: const TextStyle(fontWeight: FontWeight.w600),
                                    ),
                                  ),
                                )
                              : ListView.builder(
                                  scrollDirection: Axis.horizontal,
                                  padding: const EdgeInsets.symmetric(horizontal: 16),
                                  itemCount: state.plots.length,
                                  itemBuilder: (ctx, idx) {
                                    final plot = state.plots[idx];
                                    return _buildPlotHorizontalCard(plot, state, locale);
                                  },
                                ),
                        ),
                      ],
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.only(left: 16, right: 16, bottom: 100, top: 4),
                      itemCount: state.plots.length,
                      itemBuilder: (ctx, idx) {
                        final plot = state.plots[idx];
                        return _buildPlotVerticalCard(plot, state, locale);
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLangBtn(String code, String label, String current) {
    final active = code == current;
    return GestureDetector(
      onTap: () => widget.state.setLocale(code),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: active ? AnyqColors.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: active ? Colors.white : AnyqColors.inkMute,
            fontSize: 11,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }

  Widget _buildFilterChip({required String label, required bool selected, required VoidCallback onTap}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFF0F2942) : Colors.white,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: selected ? const Color(0xFF0F2942) : const Color(0x33CBD5E1)),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? Colors.white : AnyqColors.ink,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  Widget _buildPlotHorizontalCard(Plot plot, AppState state, String locale) {
    final isSelected = state.selectedPlot?.id == plot.id;

    return Container(
      width: 290,
      margin: const EdgeInsets.only(right: 12),
      child: GlassContainer(
        level: GlassLevel.l2,
        padding: const EdgeInsets.all(12),
        customBorder: isSelected ? Border.all(color: AnyqColors.gold, width: 2) : null,
        onTap: () => state.selectPlot(plot),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        plot.title(locale),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AnyqColors.ink,
                          fontWeight: FontWeight.w700,
                          fontSize: 14,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${plot.district} · ${plot.areaSotka} соток',
                        style: const TextStyle(
                          color: AnyqColors.inkMute,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: Icon(
                    plot.isFavorite ? Icons.favorite : Icons.favorite_border,
                    size: 20,
                    color: plot.isFavorite ? Colors.red : AnyqColors.inkMute,
                  ),
                  onPressed: () => state.toggleFavorite(plot),
                  constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
                  padding: EdgeInsets.zero,
                ),
              ],
            ),
            const SizedBox(height: 6),
            ClarityBadge(
              verified: plot.verified,
              hasRestrictions: plot.hasRestrictions,
              trustScore: plot.trustScore,
              locale: locale,
            ),
            const Spacer(),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${_formatPrice(plot.priceKzt)} ₸',
                      style: const TextStyle(
                        color: AnyqColors.primary,
                        fontWeight: FontWeight.w800,
                        fontSize: 15,
                      ),
                    ),
                    Text(
                      plot.maskedCadastral,
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        color: Color(0xFF64748B),
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
                ElevatedButton(
                  onPressed: () => state.selectPlot(plot),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AnyqColors.primary,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    elevation: 0,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        locale == 'kk' ? 'Паспорт' : 'Паспорт',
                        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(width: 4),
                      const Icon(Icons.arrow_forward, size: 12),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPlotVerticalCard(Plot plot, AppState state, String locale) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      child: GlassContainer(
        level: GlassLevel.l2,
        padding: const EdgeInsets.all(16),
        onTap: () => state.selectPlot(plot),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    plot.title(locale),
                    style: const TextStyle(
                      color: AnyqColors.ink,
                      fontWeight: FontWeight.w700,
                      fontSize: 16,
                    ),
                  ),
                ),
                IconButton(
                  icon: Icon(
                    plot.isFavorite ? Icons.favorite : Icons.favorite_border,
                    color: plot.isFavorite ? Colors.red : AnyqColors.inkMute,
                  ),
                  onPressed: () => state.toggleFavorite(plot),
                ),
              ],
            ),
            Text(
              '${plot.district} · ${plot.areaSotka} соток (${plot.landCategory})',
              style: const TextStyle(color: AnyqColors.inkMute, fontSize: 13),
            ),
            const SizedBox(height: 10),
            ClarityBadge(
              verified: plot.verified,
              hasRestrictions: plot.hasRestrictions,
              trustScore: plot.trustScore,
              locale: locale,
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                _buildUtilIcon(Icons.bolt, plot.electricity == 'connected', 'Свет'),
                const SizedBox(width: 8),
                _buildUtilIcon(Icons.local_fire_department, plot.gas == 'connected', 'Газ'),
                const SizedBox(width: 8),
                _buildUtilIcon(Icons.water_drop, plot.water == 'connected', 'Вода'),
                const SizedBox(width: 8),
                _buildUtilIcon(Icons.alt_route, plot.accessRoad == 'connected', 'Дорога'),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${_formatPrice(plot.priceKzt)} ₸',
                      style: const TextStyle(
                        color: AnyqColors.primary,
                        fontWeight: FontWeight.w800,
                        fontSize: 18,
                      ),
                    ),
                    Text(
                      plot.maskedCadastral,
                      style: const TextStyle(
                        fontFamily: 'monospace',
                        color: Color(0xFF64748B),
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
                ElevatedButton.icon(
                  onPressed: () => state.selectPlot(plot),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AnyqColors.primary,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  ),
                  icon: const Icon(Icons.shield_outlined, size: 16),
                  label: Text(
                    locale == 'kk' ? 'Төлқұжат' : 'Паспорт риска',
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUtilIcon(IconData icon, bool active, String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: active ? const Color(0xFFECFDF5) : const Color(0xFFF1F5F9),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: active ? const Color(0x66059669) : const Color(0x33CBD5E1),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: active ? AnyqColors.clarity : AnyqColors.inkMute),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: active ? const Color(0xFF065F46) : AnyqColors.inkMute,
            ),
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
