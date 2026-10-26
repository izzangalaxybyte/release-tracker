import 'package:flutter/material.dart';

import '../config.dart';
import '../format.dart';
import '../notifications.dart';
import '../poller.dart';
import '../watchlist_model.dart';
import 'search_screen.dart';
import 'upcoming_screen.dart';
import 'watchlist_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.model, required this.poller, required this.notifier});

  final WatchlistModel model;
  final Poller poller;
  final Notifier notifier;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  static const _titles = ['Watchlist', 'Upcoming', 'Search'];
  int _tab = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.model.refresh();
    _pollQuietly();
    WidgetsBinding.instance.addPostFrameCallback((_) => widget.notifier.requestPermission());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      widget.model.refresh();
      _pollQuietly();
    }
  }

  /// Opening the app also catches up on the feed, in case a background poll was delayed.
  Future<void> _pollQuietly() async {
    try {
      await widget.poller.poll();
    } catch (e) {
      debugPrint('Foreground poll failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titles[_tab]),
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline),
            tooltip: 'About and notifications',
            onPressed: () => showModalBottomSheet(
              context: context,
              showDragHandle: true,
              isScrollControlled: true,
              builder: (_) => AboutSheet(poller: widget.poller),
            ),
          ),
        ],
      ),
      body: IndexedStack(
        index: _tab,
        children: [
          WatchlistScreen(model: widget.model),
          UpcomingScreen(model: widget.model),
          SearchScreen(model: widget.model),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.list_alt), label: 'Watchlist'),
          NavigationDestination(icon: Icon(Icons.event), label: 'Upcoming'),
          NavigationDestination(icon: Icon(Icons.search), label: 'Search'),
        ],
      ),
    );
  }
}

class AboutSheet extends StatefulWidget {
  const AboutSheet({super.key, required this.poller});

  final Poller poller;

  @override
  State<AboutSheet> createState() => _AboutSheetState();
}

class _AboutSheetState extends State<AboutSheet> {
  DateTime? _lastPoll;
  bool _checking = false;
  String? _result;

  @override
  void initState() {
    super.initState();
    widget.poller.lastPollAt().then((t) => mounted ? setState(() => _lastPoll = t) : null);
  }

  Future<void> _checkNow() async {
    setState(() {
      _checking = true;
      _result = null;
    });
    try {
      final shown = await widget.poller.poll();
      _result = shown == 0 ? 'No new releases' : '$shown new notification${shown == 1 ? '' : 's'}';
      _lastPoll = await widget.poller.lastPollAt();
    } catch (e) {
      _result = 'Check failed: $e';
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final now = DateTime.now().toUtc();
    final times = Config.pollTimes
        .map((t) => formatTime(DateTime.utc(now.year, now.month, now.day, t.hour, t.minute)))
        .join(' and ');
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Notifications', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text('Checks for new releases daily at about $times, and whenever you open the app.'),
            const SizedBox(height: 4),
            Text(
              _lastPoll == null ? 'Not checked yet' : 'Last checked ${formatWhen(_lastPoll!)}',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            Row(children: [
              FilledButton.tonalIcon(
                onPressed: _checking ? null : _checkNow,
                icon: _checking
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.refresh),
                label: const Text('Check now'),
              ),
              const SizedBox(width: 12),
              if (_result != null) Flexible(child: Text(_result!)),
            ]),
            const SizedBox(height: 12),
            Text(
              'Notifications late or missing? Some phones (Xiaomi, Oppo, Vivo, Infinix, Tecno…) stop '
              'background work. In Settings › Apps › Release Tracker › Battery, choose "Unrestricted".',
              style: theme.textTheme.bodySmall,
            ),
            const Divider(height: 32),
            Text('Data sources', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            const Text('Anime from AniList (anilist.co).\n'
                'TV from TVmaze (tvmaze.com), licensed CC BY-SA.\n'
                'Manga from MangaDex (mangadex.org), with chapters by MANGA Plus and the scanlation '
                'groups who upload them.'),
          ],
        ),
      ),
    );
  }
}
