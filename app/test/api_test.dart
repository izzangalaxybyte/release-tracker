import 'package:flutter_test/flutter_test.dart';
import 'package:release_tracker/api.dart';
import 'package:release_tracker/format.dart';

import 'fakes.dart';

void main() {
  late FakeBackend backend;
  late ApiClient api;

  setUp(() {
    backend = FakeBackend();
    api = backend.client();
  });

  test('sends the bearer token and parses watchlist items', () async {
    backend.watchlist.add(FakeBackend.item('anilist', '21', 'ONE PIECE',
        last: {'label': 'Episode 1180', 'released_at': '2026-09-27T14:16:00Z'},
        next: {'label': 'Episode 1181', 'at': '2027-01-03T14:16:00Z'}));
    final items = await api.watchlist();
    expect(backend.requests.single.headers['authorization'], 'Bearer $token');
    expect(items.single.ref, 'anilist#21');
    expect(items.single.last!.at, DateTime.utc(2026, 9, 27, 14, 16));
    expect(items.single.next!.label, 'Episode 1181');
  });

  test('wrong token surfaces the API error message', () async {
    await expectLater(
      backend.client(withToken: 'nope').watchlist(),
      throwsA(isA<ApiException>().having((e) => e.status, 'status', 401).having((e) => e.message, 'message', 'unauthorized')),
    );
  });

  test('adding an existing title (409) is not an error', () async {
    final first = await api.add('anilist', '21');
    final again = await api.add('anilist', '21');
    expect(again.ref, first.ref);
    expect(backend.watchlist, hasLength(1));
  });

  test('remove tolerates an already-removed title', () async {
    await api.add('tvmaze', '32158');
    await api.remove('tvmaze', '32158');
    await api.remove('tvmaze', '32158'); // 404, ignored
    expect(backend.watchlist, isEmpty);
  });

  test('search passes type and query', () async {
    final results = await api.search('anime', 'frieren');
    expect(backend.requests.single.url.queryParameters, {'type': 'anime', 'q': 'frieren'});
    expect(results.single.title, 'Frieren');
  });

  group('format', () {
    final now = DateTime(2026, 10, 26, 12); // local noon

    test('formatWhen uses relative day names', () {
      expect(formatWhen(DateTime(2026, 10, 26, 21, 30).toUtc(), now: now), startsWith('Today'));
      expect(formatWhen(DateTime(2026, 10, 27, 5).toUtc(), now: now), startsWith('Tomorrow'));
      expect(formatWhen(DateTime(2027, 1, 3, 19, 16).toUtc(), now: now), startsWith('Sun 3 Jan 2027'));
    });

    test('formatRelative', () {
      final utcNow = DateTime.utc(2026, 10, 26, 4);
      expect(formatRelative(DateTime.utc(2026, 10, 27, 0), now: utcNow), 'in 20h');
      expect(formatRelative(DateTime.utc(2026, 9, 27, 14), now: utcNow), '28d ago');
      expect(formatRelative(DateTime.utc(2027, 1, 3), now: utcNow), 'in 2mo');
    });
  });
}
