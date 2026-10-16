import 'package:flutter_test/flutter_test.dart';
import 'package:anyq_mobile/main.dart';

void main() {
  testWidgets('ANYQ Mobile smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const AnyqApp());
    expect(find.text('ANYQ'), findsOneWidget);
  });
}
