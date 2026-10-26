/// Build-time settings, compiled in with
/// `flutter build apk --dart-define-from-file=config.local.json`.
/// config.local.json is gitignored and written by scripts/write_app_config.py.
class Config {
  static const apiBaseUrl = String.fromEnvironment('API_BASE_URL');
  static const apiToken = String.fromEnvironment('API_TOKEN');

  /// When to poll the notification feed, as UTC "HH:MM" times. Default: 30 minutes after
  /// the backend's 04:00/16:00 UTC checks (09:30 and 21:30 in Asia/Karachi).
  static const pollTimesUtc = String.fromEnvironment('POLL_TIMES_UTC', defaultValue: '04:30,16:30');

  static bool get isConfigured =>
      apiBaseUrl.startsWith('https://') && !apiBaseUrl.contains('<') && apiToken.isNotEmpty && !apiToken.contains('<');

  static List<PollTime> get pollTimes => parsePollTimes(pollTimesUtc);
}

class PollTime {
  const PollTime(this.hour, this.minute);
  final int hour;
  final int minute;

  int get minutes => hour * 60 + minute;

  @override
  bool operator ==(Object other) => other is PollTime && other.hour == hour && other.minute == minute;

  @override
  int get hashCode => minutes;

  @override
  String toString() => '${hour.toString().padLeft(2, '0')}:${minute.toString().padLeft(2, '0')}';
}

/// Parses "04:30,16:30". Invalid entries are skipped; an empty result falls back to the default.
List<PollTime> parsePollTimes(String spec) {
  final times = <PollTime>{};
  for (final part in spec.split(',')) {
    final match = RegExp(r'^\s*(\d{1,2}):(\d{2})\s*$').firstMatch(part);
    if (match == null) continue;
    final hour = int.parse(match.group(1)!);
    final minute = int.parse(match.group(2)!);
    if (hour < 24 && minute < 60) times.add(PollTime(hour, minute));
  }
  if (times.isEmpty) return const [PollTime(4, 30), PollTime(16, 30)];
  return times.toList()..sort((a, b) => a.minutes.compareTo(b.minutes));
}
