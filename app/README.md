# Release Tracker (Android app)

The Flutter client for release-tracker. Build, install and notification details are in the
[main README](../README.md#android-app).

```bash
flutter test
flutter build apk --release --dart-define-from-file=config.local.json
```

`config.local.json` holds your API URL and token. It's gitignored and created by
`scripts/write_app_config.py`. `config.example.json` shows its format.
