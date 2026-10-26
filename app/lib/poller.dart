import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:workmanager/workmanager.dart';

import 'api.dart';
import 'config.dart';
import 'notifications.dart';

const _cursorKey = 'feed_cursor';
const _lastPollKey = 'last_poll_at';
const _pollTask = 'poll-feed';

/// Minimal key-value store so the poller can be tested without platform channels.
abstract class KeyValueStore {
  Future<String?> getString(String key);
  Future<void> setString(String key, String value);
}

class PrefsStore implements KeyValueStore {
  // SharedPreferencesAsync has no in-memory cache, so the app and the background isolate
  // always see each other's writes.
  final _prefs = SharedPreferencesAsync();

  @override
  Future<String?> getString(String key) => _prefs.getString(key);

  @override
  Future<void> setString(String key, String value) => _prefs.setString(key, value);
}

String isoUtc(DateTime time) => '${time.toUtc().toIso8601String().split('.').first}Z';

/// Fetches feed rows newer than the saved cursor, shows each as a notification and advances
/// the cursor after each one. Running it twice (app + background) is harmless: notification
/// ids come from the feed id, so a repeat replaces itself rather than duplicating.
class Poller {
  Poller({required this.api, required this.notifier, required this.store, DateTime Function()? clock})
      : _clock = clock ?? DateTime.now;

  final ApiClient api;
  final Notifier notifier;
  final KeyValueStore store;
  final DateTime Function() _clock;

  /// On first launch, start the cursor at "now" so older feed rows are never shown.
  Future<void> ensureCursor() async {
    if (await store.getString(_cursorKey) == null) {
      await store.setString(_cursorKey, isoUtc(_clock()));
    }
  }

  Future<DateTime?> lastPollAt() async {
    final value = await store.getString(_lastPollKey);
    return value == null ? null : DateTime.parse(value);
  }

  /// Returns how many notifications were shown.
  Future<int> poll() async {
    var cursor = await store.getString(_cursorKey) ?? isoUtc(_clock());
    var shown = 0;
    while (true) {
      final page = await api.notifications(after: cursor);
      for (final item in page.items) {
        await notifier.show(item);
        shown++;
        cursor = item.id;
        await store.setString(_cursorKey, cursor);
      }
      if (!page.more || page.items.isEmpty) break;
    }
    await store.setString(_lastPollKey, isoUtc(_clock()));
    return shown;
  }
}

/// The first configured poll time strictly after [after], as a UTC instant.
DateTime nextPollAt(DateTime after, List<PollTime> times) {
  final utc = after.toUtc();
  for (var day = 0; day < 2; day++) {
    for (final t in times) {
      final candidate = DateTime.utc(utc.year, utc.month, utc.day + day, t.hour, t.minute);
      if (candidate.isAfter(utc)) return candidate;
    }
  }
  throw StateError('no poll times configured');
}

/// Schedules the background poll for the next poll time.
///
/// Each slot gets its own unique work name with KEEP, so scheduling the same slot again
/// (every app start) is a no-op, and a running poll never cancels itself when it schedules
/// the following slot.
Future<void> scheduleNextPoll({Duration margin = Duration.zero}) async {
  final now = DateTime.now().toUtc();
  final at = nextPollAt(now.add(margin), Config.pollTimes);
  await Workmanager().registerOneOffTask(
    'poll-${isoUtc(at)}',
    _pollTask,
    initialDelay: at.difference(now),
    existingWorkPolicy: ExistingWorkPolicy.keep,
    constraints: Constraints(networkType: NetworkType.connected),
    backoffPolicy: BackoffPolicy.exponential,
    backoffPolicyDelay: const Duration(minutes: 10),
  );
}

Poller defaultPoller(Notifier notifier) => Poller(api: ApiClient(), notifier: notifier, store: PrefsStore());

/// Background entry point: runs in its own isolate when a scheduled poll fires.
@pragma('vm:entry-point')
void callbackDispatcher() {
  Workmanager().executeTask((task, inputData) async {
    WidgetsFlutterBinding.ensureInitialized();
    // Schedule the following slot first, so the chain survives even if this poll fails.
    await scheduleNextPoll(margin: const Duration(minutes: 1));
    final notifier = Notifier();
    await notifier.init();
    try {
      await defaultPoller(notifier).poll();
      return true;
    } catch (e) {
      debugPrint('Background poll failed, will retry: $e');
      return false; // WorkManager retries with backoff
    }
  });
}
