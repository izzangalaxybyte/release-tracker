import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

const kindLabels = {'anime': 'Anime', 'manga': 'Manga', 'tv': 'TV'};
const kindIcons = {'anime': Icons.animation, 'manga': Icons.menu_book, 'tv': Icons.tv};

Future<void> openUrl(String? url) async {
  if (url == null) return;
  await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
}

/// Poster/cover thumbnail with a kind icon as placeholder.
class Cover extends StatelessWidget {
  const Cover({super.key, required this.url, required this.kind, this.width = 48});

  final String? url;
  final String kind;
  final double width;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final placeholder = Container(
      color: scheme.surfaceContainerHighest,
      alignment: Alignment.center,
      child: Icon(kindIcons[kind] ?? Icons.movie, color: scheme.onSurfaceVariant),
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: SizedBox(
        width: width,
        height: width * 1.45,
        child: url == null
            ? placeholder
            : Image.network(url!, fit: BoxFit.cover, errorBuilder: (_, _, _) => placeholder),
      ),
    );
  }
}

class KindChip extends StatelessWidget {
  const KindChip(this.kind, {super.key});

  final String kind;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(color: scheme.secondaryContainer, borderRadius: BorderRadius.circular(4)),
      child: Text(
        kindLabels[kind] ?? kind,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSecondaryContainer),
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.onSurfaceVariant;
    // A ListView so pull-to-refresh still works on an empty screen.
    return ListView(
      padding: const EdgeInsets.all(32),
      children: [
        const SizedBox(height: 80),
        Icon(icon, size: 48, color: color),
        const SizedBox(height: 12),
        Text(message, textAlign: TextAlign.center, style: TextStyle(color: color)),
      ],
    );
  }
}

class ErrorBanner extends StatelessWidget {
  const ErrorBanner(this.message, {super.key, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => MaterialBanner(
        content: Text(message),
        leading: const Icon(Icons.cloud_off),
        actions: [TextButton(onPressed: onRetry, child: const Text('Retry'))],
      );
}
