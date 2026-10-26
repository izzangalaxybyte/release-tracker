import 'package:flutter/foundation.dart';

import 'api.dart';

/// The watchlist, shared by all three tabs so adds and removes show everywhere at once.
class WatchlistModel extends ChangeNotifier {
  WatchlistModel(this.api);

  final ApiClient api;

  List<WatchItem> items = [];
  bool loading = false;
  bool loaded = false;
  String? error;

  /// Titles with a known next release, soonest first.
  List<WatchItem> get upcoming => items.where((i) => i.next?.at != null).toList()
    ..sort((a, b) => a.next!.at!.compareTo(b.next!.at!));

  bool contains(String ref) => items.any((i) => i.ref == ref);

  Future<void> refresh() async {
    loading = true;
    notifyListeners();
    try {
      items = await api.watchlist();
      error = null;
      loaded = true;
    } catch (e) {
      error = 'Couldn\'t load your watchlist: $e';
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  Future<WatchItem> add(SearchResult result) async {
    final item = await api.add(result.source, result.sourceId);
    if (!contains(item.ref)) {
      items = [...items, item]..sort((a, b) => a.title.toLowerCase().compareTo(b.title.toLowerCase()));
      notifyListeners();
    }
    return item;
  }

  /// Removes optimistically; puts the item back if the API call fails.
  Future<void> remove(WatchItem item) async {
    final before = items;
    items = items.where((i) => i.ref != item.ref).toList();
    notifyListeners();
    try {
      await api.remove(item.source, item.sourceId);
    } catch (_) {
      items = before;
      notifyListeners();
      rethrow;
    }
  }
}
