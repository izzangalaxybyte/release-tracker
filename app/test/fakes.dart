import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:release_tracker/api.dart';
import 'package:release_tracker/notifications.dart';
import 'package:release_tracker/poller.dart';

const token = 'test-token';

/// In-memory stand-in for the deployed API, with the same routes and status codes.
class FakeBackend {
  final watchlist = <Map<String, dynamic>>[];
  final feed = <Map<String, dynamic>>[];
  final requests = <http.Request>[];
  int pageSize = 100;

  ApiClient client({String withToken = token}) =>
      ApiClient(client: MockClient(_handle), baseUrl: 'https://api.test', token: withToken);

  static Map<String, dynamic> item(String source, String id, String title,
          {String kind = 'anime', Map<String, dynamic>? last, Map<String, dynamic>? next}) =>
      {'source': source, 'source_id': id, 'kind': kind, 'title': title, 'last': last, 'next': next, 'error': null};

  Future<http.Response> _handle(http.Request request) async {
    requests.add(request);
    if (request.headers['authorization'] != 'Bearer $token') return _json(401, {'error': 'unauthorized'});
    final path = request.url.path;
    final q = request.url.queryParameters;
    switch ((request.method, path)) {
      case ('GET', '/watchlist'):
        return _json(200, {'items': watchlist});
      case ('POST', '/watchlist'):
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        final existing = watchlist.where((i) => i['source_id'] == body['source_id']).firstOrNull;
        if (existing != null) return _json(409, {'item': existing});
        final added = item(body['source'] as String, body['source_id'] as String, 'Added ${body['source_id']}');
        watchlist.add(added);
        return _json(201, {'item': added});
      case ('GET', '/search'):
        return _json(200, {
          'items': [
            {'source': 'anilist', 'source_id': '154587', 'kind': q['type'], 'title': 'Frieren', 'year': 2023,
             'status': 'FINISHED', 'detail': 'TV', 'on_watchlist': false},
          ]
        });
      case ('GET', '/notifications'):
        final after = q['after'] ?? '';
        final rows = feed.where((r) => (r['id'] as String).compareTo(after) > 0).take(pageSize).toList();
        return _json(200, {'items': rows, 'cursor': rows.isEmpty ? q['after'] : rows.last['id'], 'more': rows.length == pageSize});
    }
    if (request.method == 'DELETE' && path.startsWith('/watchlist/')) {
      final id = path.split('/').last;
      final before = watchlist.length;
      watchlist.removeWhere((i) => i['source_id'] == id);
      return before == watchlist.length ? _json(404, {'error': 'not on the watchlist'}) : http.Response('', 204);
    }
    return _json(404, {'error': 'no such route'});
  }

  static http.Response _json(int status, Object body) =>
      http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json'});
}

class FakeNotifier implements Notifier {
  final shown = <FeedItem>[];

  @override
  Future<void> show(FeedItem item) async => shown.add(item);

  @override
  Future<void> init({void Function(String? url)? onTap}) async {}

  @override
  Future<String?> launchUrl() async => null;

  @override
  Future<bool> requestPermission() async => true;
}

class MemoryStore implements KeyValueStore {
  final values = <String, String>{};

  @override
  Future<String?> getString(String key) async => values[key];

  @override
  Future<void> setString(String key, String value) async => values[key] = value;
}
