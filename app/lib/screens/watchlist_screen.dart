import 'package:flutter/material.dart';

import '../api.dart';
import '../format.dart';
import '../watchlist_model.dart';
import '../widgets.dart';
import 'title_screen.dart';

class WatchlistScreen extends StatelessWidget {
  const WatchlistScreen({super.key, required this.model});

  final WatchlistModel model;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: model,
      builder: (context, _) {
        if (!model.loaded && model.loading) return const Center(child: CircularProgressIndicator());
        return Column(
          children: [
            if (model.error != null) ErrorBanner(model.error!, onRetry: model.refresh),
            Expanded(
              child: RefreshIndicator(
                onRefresh: model.refresh,
                child: model.items.isEmpty
                    ? const EmptyState(icon: Icons.playlist_add, message: 'Nothing on your watchlist yet.\nUse Search to add titles.')
                    : ListView.separated(
                        itemCount: model.items.length,
                        separatorBuilder: (_, _) => const Divider(height: 1, indent: 76),
                        itemBuilder: (context, i) => _DismissibleTile(item: model.items[i], model: model),
                      ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _DismissibleTile extends StatelessWidget {
  const _DismissibleTile({required this.item, required this.model});

  final WatchItem item;
  final WatchlistModel model;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Dismissible(
      key: ValueKey(item.ref),
      direction: DismissDirection.endToStart,
      background: Container(
        color: scheme.errorContainer,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 24),
        child: Icon(Icons.delete, color: scheme.onErrorContainer),
      ),
      confirmDismiss: (_) => showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Remove ${item.title}?'),
          content: const Text('You\'ll stop getting notifications for it.'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove')),
          ],
        ),
      ),
      onDismissed: (_) async {
        final messenger = ScaffoldMessenger.of(context);
        try {
          await model.remove(item);
          messenger.showSnackBar(SnackBar(content: Text('Removed ${item.title}')));
        } catch (e) {
          messenger.showSnackBar(SnackBar(content: Text('Couldn\'t remove ${item.title}: $e')));
        }
      },
      child: WatchTile(item: item, onTap: () => openTitle(context, item, model)),
    );
  }
}

void openTitle(BuildContext context, WatchItem item, WatchlistModel model) =>
    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => TitleScreen(item: item, model: model)));

class WatchTile extends StatelessWidget {
  const WatchTile({super.key, required this.item, this.onTap});

  final WatchItem item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final last = item.last;
    final next = item.next;
    return ListTile(
      leading: Cover(url: item.image, kind: item.kind),
      title: Text(item.title, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 2),
          Row(children: [
            KindChip(item.kind),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                last == null
                    ? 'Nothing released yet'
                    : 'Latest: ${last.label}${last.at == null ? '' : ' · ${formatRelative(last.at!)}'}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: muted,
              ),
            ),
          ]),
          if (next?.at != null)
            Text('Next: ${next!.label} · ${formatWhen(next.at!)}', maxLines: 1, overflow: TextOverflow.ellipsis, style: muted),
          if (item.error != null)
            Text('Last check failed', style: muted?.copyWith(color: theme.colorScheme.error)),
        ],
      ),
      isThreeLine: next?.at != null || item.error != null,
      onTap: onTap,
    );
  }
}
