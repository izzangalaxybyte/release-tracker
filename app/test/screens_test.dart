import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:release_tracker/screens/search_screen.dart';
import 'package:release_tracker/screens/title_screen.dart';
import 'package:release_tracker/screens/upcoming_screen.dart';
import 'package:release_tracker/screens/watchlist_screen.dart';
import 'package:release_tracker/watchlist_model.dart';

import 'fakes.dart';

Widget host(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  late FakeBackend backend;
  late WatchlistModel model;

  setUp(() {
    backend = FakeBackend()
      ..watchlist.addAll([
        FakeBackend.item('tvmaze', '32158', 'FBI', kind: 'tv', url: 'https://www.tvmaze.com/shows/32158/fbi',
            last: {'label': 'S09E03 · White Rock', 'released_at': '2026-10-20T00:00:00Z'},
            next: {'label': 'S09E04 · Reticence', 'at': '2099-10-27T00:00:00Z'}),
        FakeBackend.item('mangadex', 'a1c7c817-4e59-43b7-9365-09675a149a6f', 'One Piece', kind: 'manga',
            last: {'label': 'Chapter 1196', 'released_at': '2026-10-18T15:10:58Z'}),
      ]);
    model = WatchlistModel(backend.client());
  });

  testWidgets('watchlist shows titles with latest and next release', (tester) async {
    await model.refresh();
    await tester.pumpWidget(host(WatchlistScreen(model: model)));
    expect(find.text('FBI'), findsOneWidget);
    expect(find.text('One Piece'), findsOneWidget);
    expect(find.textContaining('Latest: Chapter 1196'), findsOneWidget);
    expect(find.textContaining('Next: S09E04 · Reticence'), findsOneWidget);
  });

  testWidgets('swipe to remove asks first, then removes', (tester) async {
    await model.refresh();
    await tester.pumpWidget(host(WatchlistScreen(model: model)));
    await tester.drag(find.text('FBI'), const Offset(-600, 0));
    await tester.pumpAndSettle();
    expect(find.text('Remove FBI?'), findsOneWidget);
    await tester.tap(find.text('Remove'));
    await tester.pumpAndSettle();
    expect(find.text('FBI'), findsNothing);
    expect(backend.watchlist.map((i) => i['title']), ['One Piece']);
  });

  testWidgets('upcoming lists only titles with a known next release', (tester) async {
    await model.refresh();
    await tester.pumpWidget(host(UpcomingScreen(model: model)));
    expect(find.text('FBI'), findsOneWidget);
    expect(find.text('One Piece'), findsNothing); // manga have no schedule
  });

  testWidgets('search then add marks the result as on the watchlist', (tester) async {
    await model.refresh();
    await tester.pumpWidget(host(SearchScreen(model: model)));
    await tester.enterText(find.byType(TextField), 'frieren');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(find.text('Frieren'), findsOneWidget);
    expect(find.text('2023 · TV · Finished'), findsOneWidget);

    await tester.tap(find.byTooltip('Add Frieren'));
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
    expect(model.contains('anilist#154587'), isTrue);
  });

  testWidgets('tapping a title shows its last 12 months of releases by month', (tester) async {
    backend.history['32158'] = [
      {'key': 'tv#3', 'label': 'S09E03 · White Rock', 'released_at': '2026-10-20T00:00:00Z', 'url': 'https://t.test/3'},
      {'key': 'tv#2', 'label': 'S09E02 · Omissions', 'released_at': '2026-10-13T00:00:00Z', 'url': 'https://t.test/2'},
      {'key': 'tv#1', 'label': 'S08E22 · Finale', 'released_at': '2026-05-19T00:00:00Z', 'url': 'https://t.test/1'},
    ];
    await model.refresh();
    await tester.pumpWidget(host(WatchlistScreen(model: model)));
    await tester.tap(find.text('FBI'));
    await tester.pumpAndSettle();

    expect(find.byType(TitleScreen), findsOneWidget);
    expect(find.text('3 releases in the last 12 months'), findsOneWidget);
    expect(find.textContaining('October 2026 · 2'), findsOneWidget);
    expect(find.textContaining('May 2026 · 1'), findsOneWidget);
    expect(find.text('S09E02 · Omissions'), findsOneWidget);
    expect(find.text('Next: S09E04 · Reticence'), findsOneWidget);
    expect(find.byTooltip('Open on TVmaze'), findsOneWidget);
  });

  testWidgets('manga detail explains the missing schedule; remove pops back', (tester) async {
    await model.refresh();
    await tester.pumpWidget(host(WatchlistScreen(model: model)));
    await tester.tap(find.text('One Piece'));
    await tester.pumpAndSettle();
    expect(find.text('No releases in the last 12 months'), findsOneWidget);
    expect(find.text('No release schedule for manga'), findsOneWidget);

    await tester.tap(find.byTooltip('Remove from watchlist'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Remove'));
    await tester.pumpAndSettle();
    expect(find.byType(TitleScreen), findsNothing);
    expect(find.text('One Piece'), findsNothing);
    expect(backend.watchlist.map((i) => i['title']), ['FBI']);
  });
}
