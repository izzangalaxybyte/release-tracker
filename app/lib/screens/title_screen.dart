import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../api.dart';
import '../format.dart';
import '../watchlist_model.dart';
import '../widgets.dart';

/// One title: its next release and every release from the last 12 months, by month.
class TitleScreen extends StatefulWidget {
  const TitleScreen({super.key, required this.item, required this.model});

  final WatchItem item;
  final WatchlistModel model;

  @override
  State<TitleScreen> createState() => _TitleScreenState();
}

class _TitleScreenState extends State<TitleScreen> {
  late Future<ReleaseHistory> _history = _load();

  Future<ReleaseHistory> _load() => widget.model.api.releases(widget.item.source, widget.item.sourceId);

  Future<void> _reload() async {
    final next = _load();
    setState(() => _history = next);
    await next.catchError((_) => ReleaseHistory([], DateTime.now(), null));
  }

  Future<void> _remove() async {
    final item = widget.item;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Remove ${item.title}?'),
        content: const Text('You\'ll stop getting notifications for it.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    final navigator = Navigator.of(context);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.model.remove(item);
      navigator.pop();
      messenger.showSnackBar(SnackBar(content: Text('Removed ${item.title}')));
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Couldn\'t remove ${item.title}: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    return Scaffold(
      appBar: AppBar(
        title: Text(item.title, maxLines: 1, overflow: TextOverflow.ellipsis),
        actions: [
          if (item.url != null)
            IconButton(
              icon: const Icon(Icons.open_in_new),
              tooltip: 'Open on ${sourceNames[item.source] ?? item.source}',
              onPressed: () => openUrl(item.url),
            ),
          if (widget.model.contains(item.ref))
            IconButton(icon: const Icon(Icons.delete_outline), tooltip: 'Remove from watchlist', onPressed: _remove),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: FutureBuilder<ReleaseHistory>(
          future: _history,
          builder: (context, snapshot) => ListView(
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              _Header(item: item, next: snapshot.data?.next ?? item.next),
              ..._body(context, snapshot),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _body(BuildContext context, AsyncSnapshot<ReleaseHistory> snapshot) {
    final theme = Theme.of(context);
    if (snapshot.hasError) {
      return [
        ListTile(
          leading: Icon(Icons.cloud_off, color: theme.colorScheme.error),
          title: Text('Couldn\'t load releases: ${snapshot.error}'),
          trailing: TextButton(onPressed: _reload, child: const Text('Retry')),
        ),
      ];
    }
    if (!snapshot.hasData) {
      return const [Padding(padding: EdgeInsets.all(48), child: Center(child: CircularProgressIndicator()))];
    }
    final releases = snapshot.data!.items;
    final rows = <Widget>[
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
        child: Text(
          releases.isEmpty
              ? 'No releases in the last 12 months'
              : '${releases.length} release${releases.length == 1 ? '' : 's'} in the last 12 months',
          style: theme.textTheme.titleMedium,
        ),
      ),
    ];
    String monthOf(HistoryRelease r) => r.at == null ? 'Date unknown' : DateFormat.yMMMM().format(r.at!.toLocal());
    final perMonth = <String, int>{};
    for (final release in releases) {
      perMonth.update(monthOf(release), (n) => n + 1, ifAbsent: () => 1);
    }
    String? month;
    for (final release in releases) {
      final heading = monthOf(release);
      if (heading != month) {
        month = heading;
        final count = perMonth[heading];
        rows.add(Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: Text('$heading · $count', style: theme.textTheme.labelLarge?.copyWith(color: theme.colorScheme.primary)),
        ));
      }
      rows.add(ListTile(
        dense: true,
        title: Text(release.label, maxLines: 1, overflow: TextOverflow.ellipsis),
        trailing: Text(release.at == null ? '' : formatWhen(release.at!), style: theme.textTheme.bodySmall),
        onTap: release.url == null ? null : () => openUrl(release.url),
      ));
    }
    if (widget.item.kind == 'manga') {
      rows.add(Padding(
        padding: const EdgeInsets.all(16),
        child: Text(
          'Only chapters uploaded to MangaDex are listed. For some series that is just the latest '
          'official chapters.',
          style: theme.textTheme.bodySmall,
        ),
      ));
    }
    return rows;
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.item, required this.next});

  final WatchItem item;
  final ReleaseInfo? next;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final status = item.status?.replaceAll('_', ' ').toLowerCase();
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Cover(url: item.image, kind: item.kind, width: 96),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.title, style: theme.textTheme.titleLarge),
                const SizedBox(height: 6),
                Row(children: [
                  KindChip(item.kind),
                  if (status != null) ...[
                    const SizedBox(width: 8),
                    Text(status[0].toUpperCase() + status.substring(1), style: theme.textTheme.bodySmall),
                  ],
                ]),
                const SizedBox(height: 12),
                if (next?.at != null)
                  Card.filled(
                    margin: EdgeInsets.zero,
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Next: ${next!.label}', style: theme.textTheme.titleSmall),
                          Text('${formatWhen(next!.at!)} · ${formatRelative(next!.at!)}', style: theme.textTheme.bodySmall),
                        ],
                      ),
                    ),
                  )
                else
                  Text(item.kind == 'manga' ? 'No release schedule for manga' : 'No next release announced',
                      style: theme.textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
