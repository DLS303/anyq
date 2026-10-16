class PlotPoint {
  final double lat;
  final double lng;

  const PlotPoint(this.lat, this.lng);

  factory PlotPoint.fromJson(List<dynamic> json) {
    return PlotPoint(
      (json[0] as num).toDouble(),
      (json[1] as num).toDouble(),
    );
  }
}

class Plot {
  final String id;
  final String slug;
  final String ownerId;
  final String cadastralNo;
  final String titleRu;
  final String titleKk;
  final String district;
  final String purpose;
  final double areaSotka;
  final int priceKzt;
  final bool divisible;
  final String landCategory;
  final String status;
  final bool verified;
  final int trustScore;
  final String electricity;
  final String gas;
  final String water;
  final String sewage;
  final String accessRoad;
  final String relief;
  final String soil;
  final String encumbrances;
  final bool registeredBuildings;
  final bool redLines;
  final bool powerProtectionZone;
  final bool gasProtectionZone;
  final bool waterProtection;
  final String descriptionRu;
  final String descriptionKk;
  final List<PlotPoint> polygon;
  final List<String> photos;
  bool isUnlocked; // Has user paid Kaspi report?
  bool isFavorite;

  Plot({
    required this.id,
    required this.slug,
    required this.ownerId,
    required this.cadastralNo,
    required this.titleRu,
    required this.titleKk,
    required this.district,
    required this.purpose,
    required this.areaSotka,
    required this.priceKzt,
    required this.divisible,
    required this.landCategory,
    required this.status,
    required this.verified,
    required this.trustScore,
    required this.electricity,
    required this.gas,
    required this.water,
    required this.sewage,
    required this.accessRoad,
    required this.relief,
    required this.soil,
    required this.encumbrances,
    required this.registeredBuildings,
    required this.redLines,
    required this.powerProtectionZone,
    required this.gasProtectionZone,
    required this.waterProtection,
    required this.descriptionRu,
    required this.descriptionKk,
    required this.polygon,
    required this.photos,
    this.isUnlocked = false,
    this.isFavorite = false,
  });

  String get maskedCadastral {
    if (isUnlocked) return cadastralNo;
    final parts = cadastralNo.split('-');
    if (parts.length >= 4) {
      return '${parts[0]}-${parts[1]}-•••-•••';
    }
    return '20-315-•••-•••';
  }

  String title(String locale) => locale == 'kk' ? titleKk : titleRu;
  String description(String locale) => locale == 'kk' ? descriptionKk : descriptionRu;

  bool get hasRestrictions => redLines || powerProtectionZone || waterProtection || encumbrances.isNotEmpty;

  factory Plot.fromJson(Map<String, dynamic> json) {
    var rawPolygon = json['polygon'] as List<dynamic>? ?? [];
    List<PlotPoint> pts = rawPolygon.map((p) => PlotPoint.fromJson(p as List<dynamic>)).toList();

    var rawPhotos = json['photos'] as List<dynamic>? ?? [];
    List<String> ph = rawPhotos.map((e) => e.toString()).toList();

    return Plot(
      id: json['id'] ?? '',
      slug: json['slug'] ?? '',
      ownerId: json['owner_id'] ?? '',
      cadastralNo: json['cadastral_no'] ?? '',
      titleRu: json['title_ru'] ?? '',
      titleKk: json['title_kk'] ?? '',
      district: json['district'] ?? '',
      purpose: json['purpose'] ?? 'izhs',
      areaSotka: (json['area_sotka'] as num?)?.toDouble() ?? 0.0,
      priceKzt: (json['price_kzt'] as num?)?.toInt() ?? 0,
      divisible: json['divisible'] ?? false,
      landCategory: json['land_category'] ?? '',
      status: json['status'] ?? 'published',
      verified: json['verified'] ?? false,
      trustScore: (json['trust_score'] as num?)?.toInt() ?? 50,
      electricity: json['electricity'] ?? 'absent',
      gas: json['gas'] ?? 'absent',
      water: json['water'] ?? 'absent',
      sewage: json['sewage'] ?? 'absent',
      accessRoad: json['access_road'] ?? 'connected',
      relief: json['relief'] ?? 'flat',
      soil: json['soil'] ?? '',
      encumbrances: json['encumbrances'] ?? '',
      registeredBuildings: json['registered_buildings'] ?? false,
      redLines: json['red_lines'] ?? false,
      powerProtectionZone: json['power_protection_zone'] ?? false,
      gasProtectionZone: json['gas_protection_zone'] ?? false,
      waterProtection: json['water_protection'] ?? false,
      descriptionRu: json['description_ru'] ?? '',
      descriptionKk: json['description_kk'] ?? '',
      polygon: pts,
      photos: ph,
    );
  }
}
