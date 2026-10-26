import 'package:flutter/material.dart';

import '../api.dart';
import '../format.dart';
import '../watchlist_model.dart';
import '../widgets.dart';
import 'watchlist_screen.dart' show openTitle;

class UpcomingScreen extends StatelessWidget {
  const UpcomingScreen({super.key, required this.model});

  final WatchlistModel model;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: model,
      builder: (context, _) {
        if (!model.loaded && model.loading) return const Center(child: CircularProgressIndicator());
        final items = model.upcoming;
        // Flatten into day headers followed by that day's releases.
        final rows = <Object>[];
        String? day;
        for (final item in items) {
          final heading = formatDay(item.next!.at!);
          if (heading != day) rows.add(day = heading);
          rows.add(item);
        }
        return RefreshIndicator(
          onRefresh: model.refresh,
          child: items.isEmpty
              ? const EmptyState(
                  icon: Icons.event_available,
                  message: 'No announced releases.\nManga never show here: MangaDex has no release schedule.',
                )
              : ListView.builder(
                  itemCount: rows.length,
                  itemBuilder: (context, i) {
                    final row = rows[i];
                    if (row is String) {
                      return Padding(
                        padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
                        child: Text(row, style: Theme.of(context).textTheme.titleSmall),
                      );
                    }
                    return _UpcomingTile(item: row as WatchItem, model: model);
                  },
                ),
        );
      },
    );
  }
}

class _UpcomingTile extends StatelessWidget {
  const _UpcomingTile({required this.item, required this.model});

  final WatchItem item;
  final WatchlistModel model;

  @override
  Widget build(BuildContext context) {
    final next = item.next!;
    final theme = Theme.of(context);
    return ListTile(
      leading: Cover(url: item.image, kind: item.kind, width: 40),
      title: Text(item.title, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(next.label, maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(formatTime(next.at!), style: theme.textTheme.titleSmall),
          Text(formatRelative(next.at!), style: theme.textTheme.bodySmall),
        ],
      ),
      onTap: () => openTitle(context, item, model),
    );
  }
}
