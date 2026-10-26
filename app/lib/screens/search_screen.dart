import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../watchlist_model.dart';
import '../widgets.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.model});

  final WatchlistModel model;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _controller = TextEditingController();
  Timer? _debounce;
  String _kind = 'anime';
  List<SearchResult> _results = [];
  bool _searching = false;
  String? _error;
  final _adding = <String>{};
  int _generation = 0; // ignore responses from searches that were superseded

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 500), _search);
  }

  Future<void> _search() async {
    _debounce?.cancel();
    final query = _controller.text.trim();
    final generation = ++_generation;
    if (query.isEmpty) {
      setState(() => _results = []);
      return;
    }
    setState(() {
      _searching = true;
      _error = null;
    });
    try {
      final results = await widget.model.api.search(_kind, query);
      if (generation == _generation) setState(() => _results = results);
    } catch (e) {
      if (generation == _generation) setState(() => _error = 'Search failed: $e');
    } finally {
      if (generation == _generation) setState(() => _searching = false);
    }
  }

  Future<void> _add(SearchResult result) async {
    setState(() => _adding.add(result.ref));
    final messenger = ScaffoldMessenger.of(context);
    try {
      await widget.model.add(result);
      messenger.showSnackBar(SnackBar(content: Text('Added ${result.title}')));
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('Couldn\'t add ${result.title}: $e')));
    } finally {
      if (mounted) setState(() => _adding.remove(result.ref));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
          child: SegmentedButton<String>(
            segments: [
              for (final kind in ['anime', 'manga', 'tv'])
                ButtonSegment(value: kind, label: Text(kindLabels[kind]!), icon: Icon(kindIcons[kind])),
            ],
            selected: {_kind},
            onSelectionChanged: (selection) {
              setState(() => _kind = selection.first);
              _search();
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: TextField(
            controller: _controller,
            textInputAction: TextInputAction.search,
            onChanged: _onChanged,
            onSubmitted: (_) => _search(),
            decoration: InputDecoration(
              hintText: 'Search ${kindLabels[_kind]!.toLowerCase()} titles',
              prefixIcon: const Icon(Icons.search),
              border: const OutlineInputBorder(),
              suffixIcon: _searching
                  ? const Padding(padding: EdgeInsets.all(14), child: CircularProgressIndicator(strokeWidth: 2))
                  : null,
            ),
          ),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        Expanded(
          child: ListenableBuilder(
            listenable: widget.model,
            builder: (context, _) => ListView.builder(
              itemCount: _results.length,
              itemBuilder: (context, i) => _resultTile(_results[i]),
            ),
          ),
        ),
      ],
    );
  }

  Widget _resultTile(SearchResult r) {
    final watched = widget.model.contains(r.ref);
    final facts = [if (r.year != null) '${r.year}', if (r.detail != null) r.detail!, if (r.status != null) _status(r.status!)];
    final Widget trailing;
    if (watched) {
      trailing = Icon(Icons.check_circle, color: Theme.of(context).colorScheme.primary, semanticLabel: 'On watchlist');
    } else if (_adding.contains(r.ref)) {
      trailing = const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2));
    } else {
      trailing = IconButton(icon: const Icon(Icons.add_circle_outline), tooltip: 'Add ${r.title}', onPressed: () => _add(r));
    }
    return ListTile(
      leading: Cover(url: r.image, kind: r.kind, width: 40),
      title: Text(r.title, maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: Text(facts.join(' · '), maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: trailing,
    );
  }

  static String _status(String status) {
    final words = status.replaceAll('_', ' ').toLowerCase();
    return words[0].toUpperCase() + words.substring(1);
  }
}
