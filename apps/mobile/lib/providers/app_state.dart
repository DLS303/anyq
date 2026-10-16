import 'package:flutter/material.dart';
import '../models/plot.dart';
import '../models/site_project.dart';
import '../services/mock_data.dart';
import '../services/api_service.dart';

class AppState extends ChangeNotifier {
  String _locale = 'ru';
  String _currentRole = 'buyer';
  int _currentTab = 0;

  List<Plot> _plots = [];
  bool _isLoading = false;
  String? _selectedDistrict;
  bool _filterOnlyVerified = false;
  bool _filterOnlyGas = false;
  bool _filterOnlyLight = false;
  String _searchQuery = '';

  Plot? _selectedPlot;
  late SiteProject _siteProject;

  String get locale => _locale;
  String get currentRole => _currentRole;
  int get currentTab => _currentTab;
  List<Plot> get plots => _plots;
  bool get isLoading => _isLoading;
  String? get selectedDistrict => _selectedDistrict;
  bool get filterOnlyVerified => _filterOnlyVerified;
  bool get filterOnlyGas => _filterOnlyGas;
  bool get filterOnlyLight => _filterOnlyLight;
  String get searchQuery => _searchQuery;
  Plot? get selectedPlot => _selectedPlot;
  SiteProject get siteProject => _siteProject;

  AppState() {
    _siteProject = MockData.getSampleProject();
    loadPlots();
  }

  void setLocale(String lang) {
    if (_locale != lang) {
      _locale = lang;
      notifyListeners();
    }
  }

  void setRole(String role) {
    _currentRole = role;
    notifyListeners();
  }

  void setTab(int index) {
    _currentTab = index;
    notifyListeners();
  }

  void selectPlot(Plot plot) {
    _selectedPlot = plot;
    _currentTab = 1; // Switch to Risk Passport tab
    notifyListeners();
  }

  Future<void> loadPlots() async {
    _isLoading = true;
    notifyListeners();

    _plots = await ApiService.fetchPlots(
      district: _selectedDistrict,
      onlyVerified: _filterOnlyVerified ? true : null,
      onlyGas: _filterOnlyGas ? true : null,
      onlyLight: _filterOnlyLight ? true : null,
    );

    if (_searchQuery.isNotEmpty) {
      final q = _searchQuery.toLowerCase();
      _plots = _plots.where((p) {
        return p.titleRu.toLowerCase().contains(q) ||
            p.titleKk.toLowerCase().contains(q) ||
            p.district.toLowerCase().contains(q) ||
            p.cadastralNo.contains(q);
      }).toList();
    }

    if (_selectedPlot == null && _plots.isNotEmpty) {
      _selectedPlot = _plots.first;
    }

    _isLoading = false;
    notifyListeners();
  }

  void setSearchQuery(String q) {
    _searchQuery = q;
    loadPlots();
  }

  void setDistrict(String? d) {
    _selectedDistrict = d;
    loadPlots();
  }

  void toggleVerified() {
    _filterOnlyVerified = !_filterOnlyVerified;
    loadPlots();
  }

  void toggleGas() {
    _filterOnlyGas = !_filterOnlyGas;
    loadPlots();
  }

  void toggleLight() {
    _filterOnlyLight = !_filterOnlyLight;
    loadPlots();
  }

  void resetFilters() {
    _selectedDistrict = null;
    _filterOnlyVerified = false;
    _filterOnlyGas = false;
    _filterOnlyLight = false;
    _searchQuery = '';
    loadPlots();
  }

  void toggleFavorite(Plot plot) {
    plot.isFavorite = !plot.isFavorite;
    notifyListeners();
  }

  void unlockPlotReport(Plot plot) {
    plot.isUnlocked = true;
    notifyListeners();
  }

  void signKsAct(String actId) {
    for (var act in _siteProject.acts) {
      if (act.id == actId) {
        act.isSigned = true;
        act.signedDate = '16.10.2026';
        break;
      }
    }
    notifyListeners();
  }
}
