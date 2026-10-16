import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/plot.dart';
import 'mock_data.dart';

class ApiService {
  // 10.0.2.2 is Android emulator host loopback, 127.0.0.1 for desktop/web/iOS
  static String baseUrl = 'http://127.0.0.1:8010';

  static Future<List<Plot>> fetchPlots({
    String? district,
    String? purpose,
    bool? onlyVerified,
    bool? onlyGas,
    bool? onlyLight,
  }) async {
    try {
      final queryParams = <String, String>{};
      if (district != null && district.isNotEmpty) queryParams['district'] = district;
      if (purpose != null && purpose.isNotEmpty) queryParams['purpose'] = purpose;
      if (onlyVerified == true) queryParams['verified'] = 'true';
      if (onlyGas == true) queryParams['gas'] = 'connected';
      if (onlyLight == true) queryParams['electricity'] = 'connected';

      final uri = Uri.parse('$baseUrl/v1/plots').replace(queryParameters: queryParams);
      final response = await http.get(uri).timeout(const Duration(seconds: 3));

      if (response.statusCode == 200) {
        final decoded = json.decode(response.body);
        final list = decoded['data'] as List<dynamic>? ?? [];
        return list.map((item) => Plot.fromJson(item as Map<String, dynamic>)).toList();
      }
    } catch (_) {
      // Offline fallback: graceful degradation to bundled seed data
    }

    var list = MockData.getInitialPlots();
    if (district != null && district.isNotEmpty) {
      list = list.where((p) => p.district == district).toList();
    }
    if (onlyVerified == true) {
      list = list.where((p) => p.verified).toList();
    }
    if (onlyGas == true) {
      list = list.where((p) => p.gas == 'connected').toList();
    }
    if (onlyLight == true) {
      list = list.where((p) => p.electricity == 'connected').toList();
    }
    return list;
  }
}
