import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'api.dart';

/// Shows feed items as Android notifications. Tapping one opens its release page.
class Notifier {
  Notifier([FlutterLocalNotificationsPlugin? plugin]) : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  static const _details = NotificationDetails(
    android: AndroidNotificationDetails(
      'releases',
      'New releases',
      channelDescription: 'New episodes and chapters of titles you follow',
      importance: Importance.high,
      priority: Priority.high,
      icon: 'ic_stat_release',
    ),
  );

  final FlutterLocalNotificationsPlugin _plugin;

  /// [onTap] receives the tapped notification's URL (if it has one).
  Future<void> init({void Function(String? url)? onTap}) async {
    await _plugin.initialize(
      settings: const InitializationSettings(android: AndroidInitializationSettings('ic_stat_release')),
      onDidReceiveNotificationResponse: onTap == null ? null : (response) => onTap(response.payload),
    );
  }

  /// URL of the notification that launched the app, if it was launched by tapping one.
  Future<String?> launchUrl() async {
    final details = await _plugin.getNotificationAppLaunchDetails();
    return details?.didNotificationLaunchApp ?? false ? details!.notificationResponse?.payload : null;
  }

  Future<bool> requestPermission() async =>
      await _plugin
          .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission() ??
      false;

  Future<void> show(FeedItem item) => _plugin.show(
        id: notificationId(item.id),
        title: item.title,
        body: item.body,
        notificationDetails: _details,
        payload: item.url,
      );
}

/// Stable 31-bit id per feed item (FNV-1a), so showing the same item twice replaces the
/// first notification instead of duplicating it.
int notificationId(String feedId) {
  var hash = 0x811c9dc5;
  for (final unit in feedId.codeUnits) {
    hash ^= unit;
    hash = (hash * 0x01000193) & 0xffffffff;
  }
  return hash & 0x7fffffff;
}
