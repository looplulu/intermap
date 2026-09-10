import 'dart:convert';
import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:intermap_app/services/training_evidence_upload.dart';

void main() {
  late Directory root;
  late Directory session;
  const id = 'android_12345678-1234-1234-1234-123456789abc';
  setUp(() async {
    root = await Directory.systemTemp.createTemp('intermap-upload-test');
    session = await Directory('${root.path}/$id').create();
    await File('${session.path}/metadata.json').writeAsString(
      jsonEncode({
        'session_id': id,
        'schema_version': 3,
        'package_name': 'test.app',
      }),
    );
  });
  tearDown(() async {
    await root.delete(recursive: true);
  });
  String record(int n) =>
      '${jsonEncode({
        'id': 'e_$n',
        'seq': n,
        'session_id': id,
        'kind': 'accessibility',
        'payload': {'text': '我的订单'},
      })}\n';

  test('active capture batches upload without sealing the session', () async {
    await File(
      '${session.path}/journal.jsonl',
    ).writeAsString(List.generate(35, (i) => record(i + 1)).join());
    final operations = <String>[];
    final uploader = TrainingEvidenceUpload(
      client: MockClient((request) async {
        final data = jsonDecode(request.body);
        operations.add(data['operation']);
        expect(data['password'], 'test-password');
        return http.Response(
          jsonEncode({'ok': true, 'accepted_seq': data['records'].last['seq']}),
          200,
        );
      }),
    )..rootOverride = root.path;
    await uploader.sync('test-password', activeSession: id);
    expect(operations, ['append', 'append', 'append']);
    expect(
      jsonDecode(
        await File('${session.path}/upload_ack.json').readAsString(),
      )['seq'],
      35,
    );
    await uploader.sync('test-password', activeSession: id);
    expect(operations.length, 3);
    uploader.dispose();
  });

  test('failed HTTP acknowledgement never advances the local cursor', () async {
    await File('${session.path}/journal.jsonl').writeAsString(record(1));
    var fails = true;
    final uploader = TrainingEvidenceUpload(
      client: MockClient((request) async {
        final data = jsonDecode(request.body);
        if (fails) return http.Response('{}', 503);
        return http.Response(
          jsonEncode({'ok': true, 'accepted_seq': data['records'].last['seq']}),
          200,
        );
      }),
    )..rootOverride = root.path;
    await uploader.sync('test-password', activeSession: id);
    expect(await File('${session.path}/upload_ack.json').exists(), isFalse);
    fails = false;
    await uploader.sync('test-password', activeSession: id);
    expect(
      jsonDecode(
        await File('${session.path}/upload_ack.json').readAsString(),
      )['seq'],
      1,
    );
    uploader.dispose();
  });

  test(
    'crashed partial tail is retained and explicitly reported on finish',
    () async {
      await File(
        '${session.path}/journal.jsonl',
      ).writeAsString('${record(1)}{"seq":');
      Map? finish;
      final uploader = TrainingEvidenceUpload(
        client: MockClient((request) async {
          final data = jsonDecode(request.body) as Map;
          if (data['operation'] == 'finish') finish = data;
          return http.Response(
            jsonEncode({
              'ok': true,
              'accepted_seq': 1,
              'complete': data['operation'] == 'finish',
            }),
            200,
          );
        }),
      )..rootOverride = root.path;
      await uploader.sync('test-password');
      expect(finish?['interrupted'], isTrue);
      expect(finish?['truncated_tail_bytes'], 7);
      expect(
        await File('${session.path}/journal.jsonl').readAsString(),
        endsWith('{"seq":'),
      );
      expect(
        jsonDecode(
          await File('${session.path}/upload_ack.json').readAsString(),
        )['complete'],
        isTrue,
      );
      uploader.dispose();
    },
  );

  test(
    'native image bytes are attached with the corresponding frame record',
    () async {
      await Directory('${session.path}/frames').create();
      await File(
        '${session.path}/frames/f_1.jpg',
      ).writeAsBytes([255, 216, 4, 5, 255, 217]);
      await File('${session.path}/journal.jsonl').writeAsString(
        '${jsonEncode({
          'seq': 1,
          'id': 'e_1',
          'kind': 'frame',
          'payload': {'asset': 'f_1.jpg'},
        })}\n',
      );
      final uploader = TrainingEvidenceUpload(
        client: MockClient((request) async {
          final data = jsonDecode(request.body);
          expect(base64Decode(data['assets']['f_1.jpg']), [
            255,
            216,
            4,
            5,
            255,
            217,
          ]);
          return http.Response('{"ok":true,"accepted_seq":1}', 200);
        }),
      )..rootOverride = root.path;
      await uploader.sync('test-password', activeSession: id);
      expect(uploader.acknowledged, 1);
      uploader.dispose();
    },
  );
}
