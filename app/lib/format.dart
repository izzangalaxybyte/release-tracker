import 'package:intl/intl.dart';

/// Formats a UTC instant in the phone's local time zone: "Today 5:00 AM",
/// "Tomorrow 7:16 PM", "Yesterday 9:00 PM", "Sun 3 Jan, 7:16 PM" (+ year if not this year).
String formatWhen(DateTime utc, {DateTime? now}) {
  final local = utc.toLocal();
  final today = _day(now?.toLocal() ?? DateTime.now());
  final days = _day(local).difference(today).inDays;
  final time = DateFormat.jm().format(local);
  switch (days) {
    case 0:
      return 'Today $time';
    case 1:
      return 'Tomorrow $time';
    case -1:
      return 'Yesterday $time';
  }
  final date = local.year == today.year ? DateFormat('EEE d MMM') : DateFormat('EEE d MMM y');
  return '${date.format(local)}, $time';
}

/// Local time of day: "7:16 PM".
String formatTime(DateTime utc) => DateFormat.jm().format(utc.toLocal());

/// Day heading for grouped lists: "Today", "Tomorrow", "Tue 27 Oct".
String formatDay(DateTime utc, {DateTime? now}) {
  final local = utc.toLocal();
  final today = _day(now?.toLocal() ?? DateTime.now());
  final days = _day(local).difference(today).inDays;
  if (days == 0) return 'Today';
  if (days == 1) return 'Tomorrow';
  return (local.year == today.year ? DateFormat('EEE d MMM') : DateFormat('EEE d MMM y')).format(local);
}

/// "in 21h", "in 3d", "5m ago", "2mo ago".
String formatRelative(DateTime utc, {DateTime? now}) {
  final diff = utc.difference(now ?? DateTime.now().toUtc());
  final abs = diff.abs();
  final String amount;
  if (abs.inMinutes < 1) {
    return 'now';
  } else if (abs.inHours < 1) {
    amount = '${abs.inMinutes}m';
  } else if (abs.inDays < 1) {
    amount = '${abs.inHours}h';
  } else if (abs.inDays < 45) {
    amount = '${abs.inDays}d';
  } else if (abs.inDays < 365) {
    amount = '${abs.inDays ~/ 30}mo';
  } else {
    amount = '${abs.inDays ~/ 365}y';
  }
  return diff.isNegative ? '$amount ago' : 'in $amount';
}

DateTime _day(DateTime local) => DateTime(local.year, local.month, local.day);
