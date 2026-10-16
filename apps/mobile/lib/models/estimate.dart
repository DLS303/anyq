class EstimateItem {
  final String titleRu;
  final String titleKk;
  final String unit;
  final double quantity;
  final int unitPriceKzt;

  const EstimateItem({
    required this.titleRu,
    required this.titleKk,
    required this.unit,
    required this.quantity,
    required this.unitPriceKzt,
  });

  int get totalKzt => (quantity * unitPriceKzt).round();

  String title(String locale) => locale == 'kk' ? titleKk : titleRu;
}

class EstimateResult {
  final double areaM2;
  final int floors;
  final String wallMaterial;
  final int foundationKzt;
  final int wallsKzt;
  final int roofKzt;
  final int utilitiesKzt;
  final int finishingKzt;
  final List<EstimateItem> items;

  const EstimateResult({
    required this.areaM2,
    required this.floors,
    required this.wallMaterial,
    required this.foundationKzt,
    required this.wallsKzt,
    required this.roofKzt,
    required this.utilitiesKzt,
    required this.finishingKzt,
    required this.items,
  });

  int get totalKzt => foundationKzt + wallsKzt + roofKzt + utilitiesKzt + finishingKzt;

  static EstimateResult calculate({
    required double areaM2,
    required int floors,
    required String wallMaterial,
  }) {
    double matMultiplier = 1.0;
    if (wallMaterial == 'brick') matMultiplier = 1.25;
    if (wallMaterial == 'monolith') matMultiplier = 1.35;

    int foundation = (areaM2 / floors * 52000).round();
    int walls = (areaM2 * 84000 * matMultiplier).round();
    int roof = (areaM2 / floors * 42000).round();
    int utils = (areaM2 * 36000).round();
    int finishing = (areaM2 * 58000).round();

    List<EstimateItem> items = [
      EstimateItem(
        titleRu: 'Земляные работы и ленточный фундамент',
        titleKk: 'Жер жұмыстары және таспалы іргетас',
        unit: 'м³',
        quantity: areaM2 * 0.35,
        unitPriceKzt: 48000,
      ),
      EstimateItem(
        titleRu: 'Кладка наружных и внутренних стен ($wallMaterial)',
        titleKk: 'Қабырға қалау жұмыстары ($wallMaterial)',
        unit: 'м²',
        quantity: areaM2 * 2.4,
        unitPriceKzt: (35000 * matMultiplier).round(),
      ),
      EstimateItem(
        titleRu: 'Монолитные перекрытия и сейсмопояс',
        titleKk: 'Монолитті жабындар және сейсмобелдеу',
        unit: 'м³',
        quantity: areaM2 * 0.18,
        unitPriceKzt: 62000,
      ),
      EstimateItem(
        titleRu: 'Стропильная система и металлочерепица',
        titleKk: 'Шатыр жүйесі мен металл жабын',
        unit: 'м²',
        quantity: areaM2 / floors * 1.3,
        unitPriceKzt: 32000,
      ),
      EstimateItem(
        titleRu: 'Разводка электрики, водопровода и отопления',
        titleKk: 'Электр, су және жылыту желілері',
        unit: 'комплект',
        quantity: 1,
        unitPriceKzt: utils,
      ),
    ];

    return EstimateResult(
      areaM2: areaM2,
      floors: floors,
      wallMaterial: wallMaterial,
      foundationKzt: foundation,
      wallsKzt: walls,
      roofKzt: roof,
      utilitiesKzt: utils,
      finishingKzt: finishing,
      items: items,
    );
  }
}
