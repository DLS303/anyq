import 'package:flutter/material.dart';
import 'core/theme.dart';
import 'providers/app_state.dart';
import 'screens/catalog/catalog_screen.dart';
import 'screens/passport/passport_screen.dart';
import 'screens/estimates/estimates_screen.dart';
import 'screens/site/site_screen.dart';
import 'screens/cabinet/cabinet_screen.dart';
import 'widgets/luxury_nav_bar.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AnyqApp());
}

class AnyqApp extends StatefulWidget {
  const AnyqApp({super.key});

  @override
  State<AnyqApp> createState() => _AnyqAppState();
}

class _AnyqAppState extends State<AnyqApp> {
  late final AppState _appState;

  @override
  void initState() {
    super.initState();
    _appState = AppState();
  }

  @override
  void dispose() {
    _appState.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _appState,
      builder: (context, _) {
        return MaterialApp(
          title: 'ANYQ SuperApp',
          debugShowCheckedModeBanner: false,
          theme: AnyqTheme.lightTheme,
          home: MainShell(state: _appState),
        );
      },
    );
  }
}

class MainShell extends StatelessWidget {
  final AppState state;

  const MainShell({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final screens = [
      CatalogScreen(state: state),
      PassportScreen(state: state),
      EstimatesScreen(state: state),
      SiteScreen(state: state),
      CabinetScreen(state: state),
    ];

    return Scaffold(
      backgroundColor: AnyqColors.canvas,
      body: Stack(
        children: [
          // Screens Stack
          IndexedStack(
            index: state.currentTab,
            children: screens,
          ),

          // Floating Luxury Bottom Nav Bar
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: LuxuryNavBar(
              currentIndex: state.currentTab,
              onTabSelected: (index) => state.setTab(index),
              locale: state.locale,
            ),
          ),
        ],
      ),
    );
  }
}
