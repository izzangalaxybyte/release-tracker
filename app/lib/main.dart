import 'package:flutter/material.dart';
import 'package:workmanager/workmanager.dart';

import 'api.dart';
import 'config.dart';
import 'notifications.dart';
import 'poller.dart';
import 'screens/home.dart';
import 'watchlist_model.dart';
import 'widgets.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (!Config.isConfigured) {
    runApp(const _App(home: _NotConfigured()));
    return;
  }

  final notifier = Notifier();
  await notifier.init(onTap: openUrl);
  final poller = defaultPoller(notifier);
  await poller.ensureCursor();
  await Workmanager().initialize(callbackDispatcher);
  await scheduleNextPoll();
  final launchedFromUrl = await notifier.launchUrl();

  runApp(_App(home: HomeScreen(model: WatchlistModel(ApiClient()), poller: poller, notifier: notifier)));
  if (launchedFromUrl != null) await openUrl(launchedFromUrl);
}

class _App extends StatelessWidget {
  const _App({required this.home});

  final Widget home;

  @override
  Widget build(BuildContext context) {
    ThemeData theme(Brightness brightness) => ThemeData(
          colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple, brightness: brightness),
          useMaterial3: true,
        );
    return MaterialApp(
      title: 'Release Tracker',
      theme: theme(Brightness.light),
      darkTheme: theme(Brightness.dark),
      home: home,
    );
  }
}

class _NotConfigured extends StatelessWidget {
  const _NotConfigured();

  @override
  Widget build(BuildContext context) => const Scaffold(
        body: Center(
          child: Padding(
            padding: EdgeInsets.all(32),
            child: Text(
              'This build has no API settings.\n\n'
              'Run scripts/write_app_config.py, then build with\n'
              'flutter build apk --dart-define-from-file=config.local.json',
              textAlign: TextAlign.center,
            ),
          ),
        ),
      );
}
