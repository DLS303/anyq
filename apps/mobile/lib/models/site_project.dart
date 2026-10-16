class GanttStage {
  final String id;
  final String titleRu;
  final String titleKk;
  final String startDate;
  final String endDate;
  final double progress; // 0.0 to 1.0
  final bool isCompleted;

  const GanttStage({
    required this.id,
    required this.titleRu,
    required this.titleKk,
    required this.startDate,
    required this.endDate,
    required this.progress,
    required this.isCompleted,
  });

  String title(String locale) => locale == 'kk' ? titleKk : titleRu;
}

class KsAct {
  final String id;
  final String actNo;
  final String date;
  final String titleRu;
  final String titleKk;
  final int amountKzt;
  bool isSigned;
  String? signedDate;

  KsAct({
    required this.id,
    required this.actNo,
    required this.date,
    required this.titleRu,
    required this.titleKk,
    required this.amountKzt,
    this.isSigned = false,
    this.signedDate,
  });

  String title(String locale) => locale == 'kk' ? titleKk : titleRu;
}

class SiteProject {
  final String id;
  final String titleRu;
  final String titleKk;
  final String address;
  final double totalProgress;
  final List<GanttStage> stages;
  final List<KsAct> acts;

  const SiteProject({
    required this.id,
    required this.titleRu,
    required this.titleKk,
    required this.address,
    required this.totalProgress,
    required this.stages,
    required this.acts,
  });

  String title(String locale) => locale == 'kk' ? titleKk : titleRu;
}
