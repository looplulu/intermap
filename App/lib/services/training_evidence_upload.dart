import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

/// Upload immutable native journal records. Acknowledgements advance only after
/// the server has validated and persisted the records and referenced images.
class TrainingEvidenceUpload {
  static const channel = MethodChannel('com.intermap/app');
  final http.Client _client;
  final String endpoint;
  TrainingEvidenceUpload({http.Client? client, String? endpoint})
    : _client = client ?? http.Client(),
      endpoint =
          endpoint ?? 'https://loop-lulu.com/intermap/api/training-evidence';

  bool _busy = false;
  String? rootOverride;
  String message = '';
  int acknowledged = 0;
  void Function()? onChange;

  Future<void> sync(String password, {String? activeSession}) async {
    if (_busy || password.isEmpty) return;
    _busy = true;
    try {
      final rootPath =
          rootOverride ?? await channel.invokeMethod<String>('trainingRoot');
      if (rootPath == null) return;
      final root = Directory(rootPath);
      if (!await root.exists()) return;
      final dirs = await root
          .list()
          .where((f) => f is Directory)
          .cast<Directory>()
          .toList();
      // Current recording first; an old backlog must not starve new evidence.
      dirs.sort(
        (a, b) => a.path.endsWith(activeSession ?? '!')
            ? -1
            : b.path.endsWith(activeSession ?? '!')
            ? 1
            : a.path.compareTo(b.path),
      );
      for (final dir in dirs) {
        await _syncSession(dir, password, activeSession);
      }
    } catch (e) {
      message = '云端暂未确认，数据留在手机等待重传：$e';
      onChange?.call();
    } finally {
      _busy = false;
    }
  }

  Future<void> _syncSession(
    Directory dir,
    String password,
    String? activeSession,
  ) async {
    final metaFile = File('${dir.path}/metadata.json');
    final journal = File('${dir.path}/journal.jsonl');
    if (!await metaFile.exists() || !await journal.exists()) return;
    final meta =
        jsonDecode(await metaFile.readAsString()) as Map<String, dynamic>;
    final id = meta['session_id'] as String;
    final ackFile = File('${dir.path}/upload_ack.json');
    var ack = <String, dynamic>{'offset': 0, 'seq': 0};
    if (await ackFile.exists()) {
      ack = jsonDecode(await ackFile.readAsString()) as Map<String, dynamic>;
    }
    if (ack['complete'] == true) return;
    var offset = (ack['offset'] as num).toInt();
    var seq = (ack['seq'] as num).toInt();
    for (var batch = 0; batch < 12; batch++) {
      final completeLength = await _completeLength(journal);
      if (offset >= completeLength) break;
      final records = <Map<String, dynamic>>[];
      final assets = <String, String>{};
      var nextOffset = offset;
      var size = 0;
      await for (final line
          in journal
              .openRead(offset, completeLength)
              .transform(utf8.decoder)
              .transform(const LineSplitter())) {
        Map<String, dynamic> record;
        try {
          record = jsonDecode(line) as Map<String, dynamic>;
        } catch (_) {
          throw StateError('已保存的事件损坏，保留原文件等待核实');
        }
        if (record['seq'] != seq + records.length + 1) {
          throw StateError('本地事件序号不连续');
        }
        final payload = record['payload'] as Map<String, dynamic>;
        if (record['kind'] == 'frame') {
          final asset = payload['asset'] as String;
          if (!RegExp(r'^f_\d+\.jpg$').hasMatch(asset)) {
            throw StateError('画面文件名无效');
          }
          if (!assets.containsKey(asset)) {
            final data = await File('${dir.path}/frames/$asset').readAsBytes();
            assets[asset] = base64Encode(data);
            size += assets[asset]!.length;
          }
        }
        records.add(record);
        nextOffset += utf8.encode('$line\n').length;
        size += utf8.encode(line).length;
        if (records.length >= 16 || size >= 2000000) break;
      }
      if (records.isEmpty) break;
      final receipt = await _post({
        'operation': 'append',
        'password': password,
        'session_id': id,
        'metadata': meta,
        'records': records,
        'assets': assets,
      });
      final last = records.last['seq'] as int;
      if (receipt['accepted_seq'] != last) throw StateError('云端回执序号不匹配');
      seq = last;
      offset = nextOffset;
      ack = {'seq': seq, 'offset': offset, 'complete': false};
      await _saveAck(ackFile, ack);
      acknowledged = seq;
      message = '云端已确认 $seq 条证据，采集文件保留在手机';
      onChange?.call();
    }
    final end = File('${dir.path}/end.json');
    final ended = await end.exists();
    final completeLength = await _completeLength(journal);
    if (id != activeSession && offset >= completeLength) {
      final total = ended
          ? (jsonDecode(await end.readAsString())['total_records'] as num)
                .toInt()
          : seq;
      if (total != seq) return;
      final receipt = await _post({
        'operation': 'finish',
        'password': password,
        'session_id': id,
        'total_records': seq,
        'interrupted': !ended,
        'truncated_tail_bytes': await journal.length() - completeLength,
      });
      if (receipt['complete'] != true || receipt['accepted_seq'] != seq) {
        throw StateError('云端尚未收齐');
      }
      await _saveAck(ackFile, {...ack, 'complete': true, 'receipt': receipt});
      message = '上传成功：云端已收齐 $seq 条证据，正在后台整理，等待审核';
      onChange?.call();
    }
  }

  Future<int> _completeLength(File file) async {
    final handle = await file.open();
    try {
      var end = await handle.length();
      while (end > 0) {
        final start = end > 4096 ? end - 4096 : 0;
        await handle.setPosition(start);
        final data = await handle.read(end - start);
        final newline = data.lastIndexOf(10);
        if (newline >= 0) return start + newline + 1;
        end = start;
      }
      return 0;
    } finally {
      await handle.close();
    }
  }

  Future<Map<String, dynamic>> _post(Map<String, dynamic> payload) async {
    final response = await _client
        .post(
          Uri.parse(endpoint),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(payload),
        )
        .timeout(const Duration(seconds: 45));
    if (response.statusCode != 200) {
      throw HttpException('HTTP ${response.statusCode}');
    }
    final data = jsonDecode(response.body) as Map<String, dynamic>;
    if (data['ok'] != true) {
      throw StateError(data['error']?.toString() ?? '未确认');
    }
    return data;
  }

  Future<void> _saveAck(File file, Map<String, dynamic> value) async {
    final temp = File('${file.path}.tmp');
    await temp.writeAsString(jsonEncode(value), flush: true);
    await temp.rename(file.path);
  }

  void dispose() {
    _client.close();
  }
}
