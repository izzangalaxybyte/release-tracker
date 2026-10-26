import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart';

class ApiException implements Exception {
  ApiException(this.status, this.message);
  final int status;
  final String message;

  @override
  String toString() => message;
}

DateTime? _time(Object? value) => value is String ? DateTime.parse(value).toUtc() : null;

class ReleaseInfo {
  ReleaseInfo(this.label, this.at);
  final String label;
  final DateTime? at; // UTC

  static ReleaseInfo? fromJson(Map<String, dynamic>? json, String timeKey) =>
      json == null ? null : ReleaseInfo(json['label'] as String, _time(json[timeKey]));
}

class WatchItem {
  WatchItem({
    required this.source,
    required this.sourceId,
    required this.kind,
    required this.title,
    this.status,
    this.url,
    this.image,
    this.last,
    this.next,
    this.error,
  });

  factory WatchItem.fromJson(Map<String, dynamic> json) => WatchItem(
        source: json['source'] as String,
        sourceId: json['source_id'] as String,
        kind: json['kind'] as String,
        title: json['title'] as String,
        status: json['status'] as String?,
        url: json['url'] as String?,
        image: json['image'] as String?,
        last: ReleaseInfo.fromJson(json['last'] as Map<String, dynamic>?, 'released_at'),
        next: ReleaseInfo.fromJson(json['next'] as Map<String, dynamic>?, 'at'),
        error: json['error'] as String?,
      );

  final String source;
  final String sourceId;
  final String kind; // anime | manga | tv
  final String title;
  final String? status;
  final String? url;
  final String? image;
  final ReleaseInfo? last;
  final ReleaseInfo? next;
  final String? error;

  String get ref => '$source#$sourceId';
}

class SearchResult {
  SearchResult({
    required this.source,
    required this.sourceId,
    required this.kind,
    required this.title,
    this.year,
    this.status,
    this.image,
    this.detail,
    required this.onWatchlist,
  });

  factory SearchResult.fromJson(Map<String, dynamic> json) => SearchResult(
        source: json['source'] as String,
        sourceId: json['source_id'] as String,
        kind: json['kind'] as String,
        title: json['title'] as String,
        year: json['year'] as int?,
        status: json['status'] as String?,
        image: json['image'] as String?,
        detail: json['detail'] as String?,
        onWatchlist: json['on_watchlist'] as bool? ?? false,
      );

  final String source;
  final String sourceId;
  final String kind;
  final String title;
  final int? year;
  final String? status;
  final String? image;
  final String? detail;
  final bool onWatchlist;

  String get ref => '$source#$sourceId';
}

class FeedItem {
  FeedItem({required this.id, required this.title, required this.body, this.url, this.kind});

  factory FeedItem.fromJson(Map<String, dynamic> json) => FeedItem(
        id: json['id'] as String,
        title: json['title'] as String,
        body: json['body'] as String,
        url: json['url'] as String?,
        kind: json['kind'] as String?,
      );

  /// Feed sort key, e.g. "2026-10-26T16:00:00Z#anilist#21". Also the polling cursor.
  final String id;
  final String title;
  final String body;
  final String? url;
  final String? kind;
}

class FeedPage {
  FeedPage(this.items, this.cursor, this.more);
  final List<FeedItem> items;
  final String? cursor;
  final bool more;
}

class ApiClient {
  ApiClient({http.Client? client, String? baseUrl, String? token})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ?? Config.apiBaseUrl,
        _token = token ?? Config.apiToken;

  static const timeout = Duration(seconds: 20);

  final http.Client _client;
  final String _baseUrl;
  final String _token;

  Future<List<WatchItem>> watchlist() async =>
      _items(await _send('GET', '/watchlist')).map(WatchItem.fromJson).toList();

  Future<List<WatchItem>> upcoming() async =>
      _items(await _send('GET', '/upcoming')).map(WatchItem.fromJson).toList();

  Future<List<SearchResult>> search(String kind, String query) async =>
      _items(await _send('GET', '/search', query: {'type': kind, 'q': query})).map(SearchResult.fromJson).toList();

  /// Adds a title; a title that's already on the watchlist (409) counts as success.
  Future<WatchItem> add(String source, String sourceId) async {
    final body = await _send('POST', '/watchlist', body: {'source': source, 'source_id': sourceId}, ok: {201, 409});
    return WatchItem.fromJson(body['item'] as Map<String, dynamic>);
  }

  Future<void> remove(String source, String sourceId) =>
      _send('DELETE', '/watchlist/${Uri.encodeComponent(source)}/${Uri.encodeComponent(sourceId)}', ok: {204, 404});

  Future<FeedPage> notifications({String? after}) async {
    final body = await _send('GET', '/notifications', query: {'after': ?after});
    return FeedPage(_items(body).map(FeedItem.fromJson).toList(), body['cursor'] as String?, body['more'] as bool? ?? false);
  }

  List<Map<String, dynamic>> _items(Map<String, dynamic> body) => (body['items'] as List).cast<Map<String, dynamic>>();

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, String>? query,
    Map<String, dynamic>? body,
    Set<int> ok = const {200},
  }) async {
    final uri = Uri.parse('$_baseUrl$path').replace(queryParameters: query?.isEmpty ?? true ? null : query);
    final request = http.Request(method, uri)..headers['authorization'] = 'Bearer $_token';
    if (body != null) {
      request.headers['content-type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    final response = await http.Response.fromStream(await _client.send(request).timeout(timeout));
    final text = utf8.decode(response.bodyBytes);
    final decoded = text.isEmpty ? <String, dynamic>{} : jsonDecode(text) as Map<String, dynamic>;
    if (!ok.contains(response.statusCode)) {
      throw ApiException(response.statusCode, decoded['error'] as String? ?? 'HTTP ${response.statusCode}');
    }
    return decoded;
  }
}
