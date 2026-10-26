import 'package:flutter_test/flutter_test.dart';
import 'package:release_tracker/config.dart';
import 'package:release_tracker/notifications.dart';
import 'package:release_tracker/poller.dart';

import 'fakes.dart';

Map<String, dynamic> row(String at, String ref, String body) =>
    {'id': '$at#$ref', 'title': 'T', 'body': body, 'url': 'https://x.test/$ref', 'kind': 'anime'};

void main() {
  late FakeBackend backend;
  late FakeNotifier notifier;
  late MemoryStore store;
  late Poller poller;
  var now = DateTime.utc(2026, 10, 26, 10);

  setUp(() {
    backend = FakeBackend();
    notifier = FakeNotifier();
    store = MemoryStore();
    now = DateTime.utc(2026, 10, 26, 10);
    poller = Poller(api: backend.client(), notifier: notifier, store: store, clock: () => now);
  });

  test('first launch skips feed rows created before install', () async {
    backend.feed.add(row('2026-10-26T07:44:54Z', 'anilist#21', 'old test row'));
    await poller.ensureCursor();
    expect(await poller.poll(), 0);

    backend.feed.add(row('2026-10-26T16:00:00Z', 'anilist#21', 'Episode 1181 is out'));
    expect(await poller.poll(), 1);
    expect(notifier.shown.single.body, 'Episode 1181 is out');
  });

  test('each feed row is shown once, even across many polls', () async {
    await poller.ensureCursor();
    backend.feed.addAll([
      row('2026-10-26T16:00:00Z', 'anilist#21', 'a'),
      row('2026-10-26T16:00:00Z', 'tvmaze#32158', 'b'),
    ]);
    expect(await poller.poll(), 2);
    expect(await poller.poll(), 0);
    backend.feed.add(row('2026-10-27T04:00:00Z', 'anilist#21', 'c'));
    expect(await poller.poll(), 1);
    expect(notifier.shown.map((n) => n.body), ['a', 'b', 'c']);
    expect(await poller.lastPollAt(), now);
  });

  test('follows pagination until the feed is drained', () async {
    await poller.ensureCursor();
    backend.pageSize = 2;
    for (var i = 0; i < 5; i++) {
      backend.feed.add(row('2026-10-26T16:00:0${i}Z', 'tvmaze#$i', 'n$i'));
    }
    expect(await poller.poll(), 5);
    expect(backend.requests.where((r) => r.url.path == '/notifications').length, 3);
  });

  test('a failed poll keeps the cursor so nothing is lost', () async {
    await poller.ensureCursor();
    final cursor = await store.getString('feed_cursor');
    backend.feed.add(row('2026-10-26T16:00:00Z', 'anilist#21', 'x'));

    final unauthorized = Poller(api: backend.client(withToken: 'wrong'), notifier: notifier, store: store, clock: () => now);
    await expectLater(unauthorized.poll(), throwsA(isA<Exception>()));
    expect(await store.getString('feed_cursor'), cursor);
    expect(notifier.shown, isEmpty);

    expect(await poller.poll(), 1); // the next good poll still delivers it
  });

  group('nextPollAt', () {
    const times = [PollTime(4, 30), PollTime(16, 30)];

    test('picks the next slot today', () {
      expect(nextPollAt(DateTime.utc(2026, 10, 26, 4, 0), times), DateTime.utc(2026, 10, 26, 4, 30));
      expect(nextPollAt(DateTime.utc(2026, 10, 26, 4, 30), times), DateTime.utc(2026, 10, 26, 16, 30));
    });

    test('rolls over to tomorrow, including month ends', () {
      expect(nextPollAt(DateTime.utc(2026, 10, 31, 17, 0), times), DateTime.utc(2026, 11, 1, 4, 30));
    });

    test('accepts a local time and compares in UTC', () {
      // 09:00 in Karachi is 04:00 UTC, so the next poll is 04:30 UTC (09:30 PKT).
      final karachiNine = DateTime.utc(2026, 10, 26, 4, 0).toLocal();
      expect(nextPollAt(karachiNine, times), DateTime.utc(2026, 10, 26, 4, 30));
    });
  });

  test('parsePollTimes sorts, dedupes and falls back on garbage', () {
    expect(parsePollTimes('16:30, 04:30,16:30'), const [PollTime(4, 30), PollTime(16, 30)]);
    expect(parsePollTimes('25:00,nope'), const [PollTime(4, 30), PollTime(16, 30)]);
  });

  test('notification ids are stable and distinct', () {
    expect(notificationId('2026-10-26T16:00:00Z#anilist#21'), notificationId('2026-10-26T16:00:00Z#anilist#21'));
    expect(notificationId('2026-10-26T16:00:00Z#anilist#21'), isNot(notificationId('2026-10-26T16:00:00Z#tvmaze#1')));
    expect(notificationId('anything'), greaterThanOrEqualTo(0));
  });
}
